# k8s-autoscaler

A minimal horizontal pod autoscaler written against the official
`kubernetes` Python client. It watches average CPU utilisation of a
Deployment's pods and scales replicas toward a target utilisation.

## Prerequisites

- Python 3.8+
- `kubernetes` client (`pip install -r requirements.txt`)
- A cluster with **metrics-server** installed (the script reads the
  `metrics.k8s.io` API), or the pod CPU metric will be unavailable.

## Run

```bash
pip install -r requirements.txt
python3 autoscaler.py --namespace default --deployment my-app --min 2 --max 10 --target 60
```

In-cluster, the script auto-detects the service account via
`load_incluster_config()` and needs RBAC access to `apps/v1` deployments
and the `metrics.k8s.io` pods API.

## How it decides

```
desired = current * (avg_cpu / target_cpu)
```
clamped to `[--min, --max]`. It only scales when the computed value differs
from the current replica count, and it never scales to zero.
