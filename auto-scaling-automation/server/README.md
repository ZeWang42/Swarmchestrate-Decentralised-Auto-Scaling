# Refactored Autoscaling Experiment Server

This package contains a layered implementation with:

- `api/`: FastAPI endpoints
- `experiment/`: models and orchestration logic
- `k8s/`: Kubernetes and Prometheus operations
- `utils/`: parsing, formatting, templating helpers
- `manifests/applications/`: application manifests
- `manifests/autoscalers/`: autoscaler manifests

## Main endpoints

- `POST /deploy/bookinfo`
- `DELETE /deploy/bookinfo`
- `GET /deploy/bookinfo/status`
- `POST /deploy/bookinfo/autoscaler`
- `DELETE /deploy/bookinfo/autoscaler`
- `POST /monitor/start`
- `POST /monitor/stop`
- `GET /monitor/status`
- `POST /experiment/setup`
- `POST /experiment/cleanup`

## What changed for the custom autoscaler

The `custom` autoscaler now supports **one autoscaler Deployment per target application Deployment**:

- shared resources applied once per namespace:
  - `ServiceAccount/das-autoscaler`
  - `Role/das-autoscaler-role`
  - `RoleBinding/das-autoscaler-binding`
- one controller Deployment per target Deployment:
  - `Deployment/das-autoscaler-<target-deployment>`

This means a request with:

```json
{
  "namespace": "default",
  "deployment_names": ["reviews-v1", "ratings-v1"],
  "autoscaler_name": "custom",
  "config": {
    "image": "zewang42/das-autoscaler:latest",
    "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    "interval": 15,
    "cooldown_seconds": 30,
    "alpha_down_threshold": 30,
    "tau_min": 60,
    "tau_max": 80,
    "beta_up_threshold": 90,
    "min_replicas": 1,
    "max_replicas": 10
  }
}
```

will deploy:

- `das-autoscaler-reviews-v1`
- `das-autoscaler-ratings-v1`

## Experiment setup payload

`POST /experiment/setup` now also accepts `autoscaler.deployment_names` so experiments can target only a subset of application deployments.

Example:

```json
{
  "app": "bookinfo",
  "namespace": "default",
  "workload_name": "constant-100",
  "duration_seconds": 300,
  "autoscaler": {
    "autoscaler_name": "custom",
    "deployment_names": ["reviews-v1", "ratings-v1"],
    "config": {
      "image": "zewang42/das-autoscaler:latest",
      "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
      "interval": 15,
      "cooldown_seconds": 30,
      "alpha_down_threshold": 30,
      "tau_min": 60,
      "tau_max": 80,
      "beta_up_threshold": 90,
      "min_replicas": 1,
      "max_replicas": 10
    }
  },
  "monitor": {
    "interval": 5,
    "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    "file_prefix": "mesh_metrics"
  }
}
```

## Notes

- Replace placeholder Bookinfo manifests in `manifests/applications/bookinfo/`.
- `default_cpu` autoscaler renders an HPA manifest.
- `custom` autoscaler renders shared RBAC plus one controller Deployment per target deployment.
- Applying manifests is now idempotent for the supported autoscaler resources used in this project.
- The monitor loop writes CSV files under `/app/logs`.


## Client compatibility

The server accepts both payload styles for `/experiment/setup`:

1. New style:

```json
{
  "app": "bookinfo",
  "namespace": "default",
  "autoscaler": {
    "autoscaler_name": "custom",
    "deployment_names": ["reviews-v1", "ratings-v1"],
    "config": {
      "image": "zewang42/das-autoscaler:latest",
      "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
      "interval": 15,
      "cooldown_seconds": 30,
      "alpha_down_threshold": 30,
      "tau_min": 60,
      "tau_max": 80,
      "beta_up_threshold": 90,
      "min_replicas": 1,
      "max_replicas": 10
    }
  },
  "monitor": {
    "interval": 5,
    "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    "file_prefix": "mesh_metrics"
  }
}
```

2. Legacy client style used by `load.py`:

```json
{
  "app": "bookinfo",
  "namespace": "default",
  "hpa": {
    "mode": "cpu",
    "target_cpu_utilization": 50,
    "min_replicas": 1,
    "max_replicas": 10
  },
  "monitor": {
    "interval": 5,
    "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
    "file_prefix": "mesh_metrics"
  }
}
```

The legacy `hpa` payload is automatically translated into the server's autoscaler model. Cleanup also accepts the legacy `delete_hpa` field.


## Supported applications

This build supports both:

- `bookinfo`
- `onlineboutique`

The deploy and autoscaler APIs are now generic:

- `POST /deploy/{app_name}`
- `DELETE /deploy/{app_name}`
- `GET /deploy/{app_name}/status`
- `POST /deploy/{app_name}/autoscaler`
- `DELETE /deploy/{app_name}/autoscaler`

Examples:

```bash
curl -X POST http://<server>:8080/deploy/onlineboutique
curl -X POST http://<server>:8080/deploy/onlineboutique/autoscaler \
  -H 'content-type: application/json' \
  -d '{"namespace":"default","autoscaler_name":"default_cpu","config":{"min_replicas":1,"max_replicas":5,"average_cpu_utilization":70}}'
```

For experiment setup, use `"app": "onlineboutique"` or `"app": "bookinfo"`. If `deployment_names` is omitted, the server discovers the known deployments for the selected application.

## DA-DQN autoscaler support

This build also registers `dadqn` as an autoscaler type. Accepted aliases are:

- `dadqn`
- `da-dqn`
- `da_dqn`

DA-DQN is supported for `onlineboutique` only. When `deployment_names` is omitted, the server deploys one DA-DQN agent per supported Online Boutique microservice and skips `redis-cart`, because the upstream DA-DQN artifact ships agents/models for the 10 application services but not Redis.

Example:

```bash
curl -X POST http://<server>:8080/deploy/onlineboutique/autoscaler \
  -H 'content-type: application/json' \
  -d '{
    "namespace": "default",
    "autoscaler_name": "da-dqn",
    "config": {
      "prometheus_url": "http://prom-kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090",
      "model_host_path": "/tmp/sla_v1",
      "model_dir": "/mnt/sla_v1",
      "sample_interval_sec": 30,
      "decision_interval_sec": 15
    }
  }'
```

The server renders:

- shared `ServiceAccount`, `Role`, and `RoleBinding`
- shared `ConfigMap/dadqn-config`
- one controller Deployment per target service, named `dadqn-<service>`

The DA-DQN image defaults to:

```text
proactivellmbasedproject/dadqn-autoscaler:v4-decentralized
```

The model files must already exist on each worker at the configured hostPath, default:

```text
/tmp/sla_v1
```


## PBScaler autoscaler support

This build includes a `pbscaler` autoscaler manifest for Online Boutique. Accepted names are:

- `pbscaler`
- `pb-scaler`
- `pb_scaler`

PBScaler expects a kubeconfig file mounted from a Secret named `pbscaler-kubeconfig`. Before deploying PBScaler, create that Secret in the target namespace. If your local kubeconfig points to `https://127.0.0.1:6443`, rewrite it to the in-cluster API endpoint first:

```bash
cat ~/.kube/config \
  | sed 's#https://127.0.0.1:6443#https://kubernetes.default.svc:443#' \
  > /tmp/pbscaler-kubeconfig

kubectl create secret generic pbscaler-kubeconfig \
  --from-file=config=/tmp/pbscaler-kubeconfig \
  -n default
```

Deploy through the server:

```bash
curl -X POST http://<server>:8080/deploy/onlineboutique/autoscaler \
  -H 'content-type: application/json' \
  -d '{"namespace":"default","autoscaler_name":"pbscaler"}'
```

The rendered manifest creates:

- `Deployment/pbscaler-boutique`
- `Service/pbscaler-boutique`
- a `prometheus-proxy` sidecar that forwards `localhost:9090` to `prometheus.istio-system.svc.cluster.local:9090`

The PBScaler image defaults to:

```text
proactivellmbasedproject/pbscaler-boutique:latest
```
