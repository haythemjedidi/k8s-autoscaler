#!/usr/bin/env python3
"""k8s-autoscaler — simple metric-based horizontal autoscaler for a Deployment.

Reads average CPU utilisation of a Deployment's pods from the Kubernetes
metrics API (requires metrics-server) and adjusts replica count toward a
target utilisation, clamped between --min and --max.

Usage:
    python3 autoscaler.py --namespace default --deployment my-app \
        --min 2 --max 10 --target 60 --interval 30
"""
import argparse
import os
import time

from kubernetes import client, config


def load_kube_config():
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()   # running inside the cluster
    else:
        config.load_kube_config()        # local kubeconfig


def get_replicas(apps, namespace, name):
    return apps.read_namespaced_deployment(name, namespace).spec.replicas


def set_replicas(apps, namespace, name, replicas):
    apps.patch_namespaced_deployment_scale(
        name, namespace, {"spec": {"replicas": int(replicas)}})


def parse_cpu(value: str) -> float:
    """Convert a Kubernetes CPU quantity string to millicores."""
    value = value.strip()
    if value.endswith("n"):
        return int(value[:-1]) / 1_000_000.0   # nanocores -> millicores
    if value.endswith("u"):
        return int(value[:-1]) / 1_000.0       # microcores -> millicores
    if value.endswith("m"):
        return float(value[:-1])               # already millicores
    return float(value) * 1000.0               # whole cores -> millicores


def avg_cpu_millicores(custom, namespace, deployment):
    """Average CPU usage (millicores) across the Deployment's pods."""
    try:
        pods = custom.list_namespaced_custom_object(
            "metrics.k8s.io", "v1beta1", namespace, "pods")["items"]
    except Exception as exc:
        raise RuntimeError(
            "metrics API unavailable - is metrics-server installed?") from exc

    usages = []
    for pod in pods:
        if not pod["metadata"]["name"].startswith(deployment + "-"):
            continue
        for container in pod.get("containers", []):
            usages.append(parse_cpu(container["usage"].get("cpu", "0")))
    return sum(usages) / len(usages) if usages else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--namespace", default="default")
    parser.add_argument("--deployment", required=True)
    parser.add_argument("--min", type=int, default=1)
    parser.add_argument("--max", type=int, default=10)
    parser.add_argument("--target", type=int, default=60,
                        help="target CPU utilisation percent (default 60)")
    parser.add_argument("--interval", type=int, default=30,
                        help="seconds between evaluations (default 30)")
    args = parser.parse_args()

    load_kube_config()
    apps = client.AppsV1Api()
    custom = client.CustomObjectsApi()

    target_milli = 1000.0 * args.target / 100.0  # per-pod target, assuming 1 CPU
    while True:
        current = get_replicas(apps, args.namespace, args.deployment)
        avg_milli = avg_cpu_millicores(custom, args.namespace, args.deployment)
        desired = current
        if avg_milli > 0:
            desired = round(current * avg_milli / target_milli)
        desired = max(args.min, min(args.max, desired))
        stamp = time.strftime("%H:%M:%S")
        if desired != current:
            set_replicas(apps, args.namespace, args.deployment, desired)
            print(f"{stamp} {args.deployment}: {current} -> {desired} "
                  f"replicas (avg {avg_milli:.0f}m CPU)")
        else:
            print(f"{stamp} {args.deployment}: {current} replicas, "
                  f"avg {avg_milli:.0f}m CPU - no change")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
