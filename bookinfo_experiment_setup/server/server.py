from __future__ import annotations

import csv
import math
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from kubernetes import client, config, utils
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException


DEFAULT_NAMESPACE = os.getenv("APP_NAMESPACE", "default")

BOOKINFO_APP_NAME = "bookinfo"
BOOKINFO_MANIFEST = os.getenv("BOOKINFO_MANIFEST", "/app/manifests/bookinfo.yaml")
BOOKINFO_GATEWAY_MANIFEST = os.getenv("BOOKINFO_GATEWAY_MANIFEST", "/app/manifests/bookinfo-gateway.yaml")

PROM_URL = os.getenv("PROM_URL", "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query")
MONITOR_LOG_DIR = Path(os.getenv("MONITOR_LOG_DIR", "/app/logs"))

BOOKINFO_DEPLOYMENTS = [
    "details-v1",
    "productpage-v1",
    "ratings-v1",
    "reviews-v1",
    "reviews-v2",
    "reviews-v3",
]

app = FastAPI(title="Autoscaling Experiment Server", version="0.2.0")


class DeployAppRequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    manifest_path: str = Field(description="Path to application manifest")
    gateway_manifest_path: str | None = Field(
        default=None,
        description="Optional path to gateway/virtual service manifest",
    )
    create_namespace: bool = Field(default=False, description="Create namespace if it does not exist")


class DeployAppResponse(BaseModel):
    ok: bool
    message: str
    app: str
    namespace: str
    applied_files: list[str]
    gateway_url_hint: str | None = None


class DeployHPARequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    deployment_names: list[str] = Field(
        default_factory=lambda: BOOKINFO_DEPLOYMENTS.copy(),
        description="Deployments to attach HPA to",
    )
    min_replicas: int = Field(default=1, ge=1, description="Minimum replicas")
    max_replicas: int = Field(default=5, ge=1, description="Maximum replicas")
    average_cpu_utilization: int = Field(
        default=70,
        ge=1,
        le=100,
        description="Target average CPU utilization percentage",
    )


class DeployHPAResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    results: list[dict[str, Any]]


class DeleteHPAResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    deleted_hpas: list[str]
    missing_hpas: list[str]
    errors: list[str]


class StartMonitorRequest(BaseModel):
    namespace: str = Field(default=DEFAULT_NAMESPACE, description="Target namespace")
    interval: int = Field(default=5, ge=1, description="Sampling interval in seconds")
    prom_url: str = Field(default=PROM_URL, description="Prometheus instant query API URL")
    file_prefix: str = Field(default="mesh_metrics", description="Prefix for output CSV file name")


class MonitorStatusResponse(BaseModel):
    ok: bool
    running: bool
    namespace: str | None = None
    interval: int | None = None
    prom_url: str | None = None
    log_file: str | None = None
    started_at: str | None = None


class HPAExperimentConfig(BaseModel):
    mode: str = Field(description="none or cpu")
    target_cpu_utilization: int | None = Field(default=None, ge=1, le=100)
    min_replicas: int = Field(default=1, ge=1)
    max_replicas: int = Field(default=5, ge=1)


class MonitorExperimentConfig(BaseModel):
    interval: int = Field(default=5, ge=1)
    prom_url: str = Field(default=PROM_URL)
    file_prefix: str = Field(default="mesh_metrics")


class ExperimentSetupRequest(BaseModel):
    app: str = Field(default="bookinfo")
    namespace: str = Field(default=DEFAULT_NAMESPACE)
    request_rate: int = Field(description="Client-side load parameter, e.g. 100/300/500")
    duration_seconds: int = Field(default=120, ge=1)
    hpa: HPAExperimentConfig
    monitor: MonitorExperimentConfig = Field(default_factory=MonitorExperimentConfig)


class ExperimentSetupResponse(BaseModel):
    ok: bool
    app: str
    namespace: str
    request_rate: int
    duration_seconds: int
    hpa_mode: str
    hpa_result: dict[str, Any] | None = None
    monitor_result: dict[str, Any] | None = None
    ready_for_load: bool


class ExperimentCleanupRequest(BaseModel):
    app: str = Field(default="bookinfo")
    namespace: str = Field(default=DEFAULT_NAMESPACE)
    delete_hpa: bool = Field(default=True)
    stop_monitoring: bool = Field(default=True)


_monitor_thread: threading.Thread | None = None
_monitor_stop_event = threading.Event()
_monitor_state: dict[str, Any] = {
    "running": False,
    "namespace": None,
    "interval": None,
    "prom_url": None,
    "log_file": None,
    "started_at": None,
}


@app.on_event("startup")
def startup() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    MONITOR_LOG_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/deploy/bookinfo", response_model=DeployAppResponse)
def deploy_bookinfo(req: DeployAppRequest | None = None) -> DeployAppResponse:
    request = req or DeployAppRequest(
        namespace=DEFAULT_NAMESPACE,
        manifest_path=BOOKINFO_MANIFEST,
        gateway_manifest_path=BOOKINFO_GATEWAY_MANIFEST,
        create_namespace=False,
    )
    return _deploy_application(BOOKINFO_APP_NAME, request)


@app.delete("/deploy/bookinfo")
def delete_bookinfo(namespace: str = DEFAULT_NAMESPACE) -> dict[str, Any]:
    return _delete_application(
        BOOKINFO_APP_NAME,
        namespace,
        [BOOKINFO_GATEWAY_MANIFEST, BOOKINFO_MANIFEST],
    )


@app.get("/deploy/bookinfo/status")
def bookinfo_status(namespace: str = DEFAULT_NAMESPACE) -> dict[str, Any]:
    service_names = ["details", "productpage", "ratings", "reviews"]
    return _application_status(BOOKINFO_APP_NAME, namespace, BOOKINFO_DEPLOYMENTS, service_names)


@app.post("/deploy/bookinfo/hpa", response_model=DeployHPAResponse)
def deploy_bookinfo_hpa(req: DeployHPARequest | None = None) -> DeployHPAResponse:
    request = req or DeployHPARequest(namespace=DEFAULT_NAMESPACE)
    return _deploy_hpa_for_application(BOOKINFO_APP_NAME, request)


@app.delete("/deploy/bookinfo/hpa", response_model=DeleteHPAResponse)
def delete_bookinfo_hpa(namespace: str = DEFAULT_NAMESPACE) -> DeleteHPAResponse:
    return _delete_hpa_for_application(
        app_name=BOOKINFO_APP_NAME,
        namespace=namespace,
        deployment_names=BOOKINFO_DEPLOYMENTS,
    )


@app.post("/monitor/start", response_model=MonitorStatusResponse)
def start_monitor(req: StartMonitorRequest | None = None) -> MonitorStatusResponse:
    global _monitor_thread

    request = req or StartMonitorRequest(namespace=DEFAULT_NAMESPACE)

    if _monitor_state["running"]:
        raise HTTPException(status_code=409, detail="Monitor is already running")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_prefix = request.file_prefix.replace("/", "_").replace(" ", "_")
    log_file = MONITOR_LOG_DIR / f"{safe_prefix}_{request.namespace}_{request.interval}s_{timestamp}.csv"

    _monitor_stop_event.clear()
    _monitor_state.update(
        {
            "running": True,
            "namespace": request.namespace,
            "interval": request.interval,
            "prom_url": request.prom_url,
            "log_file": str(log_file),
            "started_at": datetime.now().isoformat(),
        }
    )

    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        kwargs={
            "namespace": request.namespace,
            "interval": request.interval,
            "prom_url": request.prom_url,
            "log_file": log_file,
        },
        daemon=True,
    )
    _monitor_thread.start()

    return MonitorStatusResponse(ok=True, **_monitor_state)


@app.post("/monitor/stop", response_model=MonitorStatusResponse)
def stop_monitor() -> MonitorStatusResponse:
    if not _monitor_state["running"]:
        raise HTTPException(status_code=409, detail="Monitor is not running")

    _monitor_stop_event.set()

    return MonitorStatusResponse(
        ok=True,
        running=False,
        namespace=_monitor_state["namespace"],
        interval=_monitor_state["interval"],
        prom_url=_monitor_state["prom_url"],
        log_file=_monitor_state["log_file"],
        started_at=_monitor_state["started_at"],
    )


@app.get("/monitor/status", response_model=MonitorStatusResponse)
def monitor_status() -> MonitorStatusResponse:
    return MonitorStatusResponse(ok=True, **_monitor_state)


@app.post("/experiment/setup", response_model=ExperimentSetupResponse)
def experiment_setup(req: ExperimentSetupRequest) -> ExperimentSetupResponse:
    if req.app != BOOKINFO_APP_NAME:
        raise HTTPException(status_code=400, detail="Only bookinfo is supported for now")

    hpa_result: dict[str, Any] | None = None

    if req.hpa.mode == "cpu":
        if req.hpa.target_cpu_utilization is None:
            raise HTTPException(status_code=400, detail="target_cpu_utilization is required when hpa.mode=cpu")

        hpa_resp = _deploy_hpa_for_application(
            BOOKINFO_APP_NAME,
            DeployHPARequest(
                namespace=req.namespace,
                deployment_names=BOOKINFO_DEPLOYMENTS,
                min_replicas=req.hpa.min_replicas,
                max_replicas=req.hpa.max_replicas,
                average_cpu_utilization=req.hpa.target_cpu_utilization,
            ),
        )
        hpa_result = hpa_resp.model_dump()

    elif req.hpa.mode != "none":
        raise HTTPException(status_code=400, detail="hpa.mode must be either 'none' or 'cpu'")

    monitor_resp = start_monitor(
        StartMonitorRequest(
            namespace=req.namespace,
            interval=req.monitor.interval,
            prom_url=req.monitor.prom_url,
            file_prefix=f"{req.monitor.file_prefix}_{req.app}_rps{req.request_rate}_hpa{req.hpa.mode}"
            + (f"{req.hpa.target_cpu_utilization}" if req.hpa.mode == "cpu" else ""),
        )
    )

    return ExperimentSetupResponse(
        ok=True,
        app=req.app,
        namespace=req.namespace,
        request_rate=req.request_rate,
        duration_seconds=req.duration_seconds,
        hpa_mode=req.hpa.mode,
        hpa_result=hpa_result,
        monitor_result=monitor_resp.model_dump(),
        ready_for_load=True,
    )


@app.post("/experiment/cleanup")
def experiment_cleanup(req: ExperimentCleanupRequest) -> dict[str, Any]:
    result: dict[str, Any] = {
        "ok": True,
        "app": req.app,
        "namespace": req.namespace,
        "monitor_stopped": None,
        "hpa_deleted": None,
        "errors": [],
    }

    if req.stop_monitoring:
        try:
            monitor_resp = stop_monitor()
            result["monitor_stopped"] = monitor_resp.model_dump()
        except Exception as exc:
            result["errors"].append(f"monitor stop failed: {str(exc)}")

    if req.delete_hpa:
        try:
            hpa_resp = _delete_hpa_for_application(
                app_name=BOOKINFO_APP_NAME,
                namespace=req.namespace,
                deployment_names=BOOKINFO_DEPLOYMENTS,
            )
            result["hpa_deleted"] = hpa_resp.model_dump()
        except Exception as exc:
            result["errors"].append(f"hpa delete failed: {str(exc)}")

    result["ok"] = len(result["errors"]) == 0
    return result


def _deploy_application(app_name: str, req: DeployAppRequest) -> DeployAppResponse:
    namespace = req.namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace must not be empty")

    manifest = Path(req.manifest_path)
    gateway_manifest = Path(req.gateway_manifest_path) if req.gateway_manifest_path else None

    if not manifest.exists():
        raise HTTPException(status_code=400, detail=f"Manifest not found: {manifest}")
    if gateway_manifest and not gateway_manifest.exists():
        raise HTTPException(status_code=400, detail=f"Gateway manifest not found: {gateway_manifest}")

    core_api = client.CoreV1Api()
    api_client = ApiClient()

    if req.create_namespace and namespace != "default":
        _ensure_namespace(core_api, namespace)

    applied_files: list[str] = []
    try:
        _apply_yaml(api_client, str(manifest), namespace)
        applied_files.append(str(manifest))

        if gateway_manifest is not None:
            _apply_yaml(api_client, str(gateway_manifest), namespace)
            applied_files.append(str(gateway_manifest))

        return DeployAppResponse(
            ok=True,
            message=f"{app_name} deployment submitted successfully",
            app=app_name,
            namespace=namespace,
            applied_files=applied_files,
            gateway_url_hint=_build_gateway_hint(namespace),
        )
    except utils.FailToCreateError as exc:
        raise HTTPException(status_code=500, detail=_format_fail_to_create(exc)) from exc
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=exc.body or str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _deploy_hpa_for_application(app_name: str, req: DeployHPARequest) -> DeployHPAResponse:
    namespace = req.namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace must not be empty")
    if req.min_replicas > req.max_replicas:
        raise HTTPException(status_code=400, detail="min_replicas cannot be greater than max_replicas")

    apps_api = client.AppsV1Api()
    results: list[dict[str, Any]] = []

    try:
        for deployment_name in req.deployment_names:
            _ensure_deployment_exists(apps_api, namespace, deployment_name)
            results.append(
                _create_or_replace_cpu_hpa(
                    namespace=namespace,
                    deployment_name=deployment_name,
                    min_replicas=req.min_replicas,
                    max_replicas=req.max_replicas,
                    average_cpu_utilization=req.average_cpu_utilization,
                )
            )

        return DeployHPAResponse(ok=True, app=app_name, namespace=namespace, results=results)
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=exc.body or str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _delete_hpa_for_application(
    app_name: str,
    namespace: str,
    deployment_names: list[str],
) -> DeleteHPAResponse:
    namespace = namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace must not be empty")

    autoscaling_api = client.AutoscalingV2Api()
    deleted_hpas: list[str] = []
    missing_hpas: list[str] = []
    errors: list[str] = []

    for deployment_name in deployment_names:
        hpa_name = f"{deployment_name}-hpa"
        try:
            autoscaling_api.delete_namespaced_horizontal_pod_autoscaler(name=hpa_name, namespace=namespace)
            deleted_hpas.append(hpa_name)
        except ApiException as exc:
            if exc.status == 404:
                missing_hpas.append(hpa_name)
            else:
                errors.append(f"{hpa_name}: {exc.body or str(exc)}")
        except Exception as exc:
            errors.append(f"{hpa_name}: {str(exc)}")

    return DeleteHPAResponse(
        ok=len(errors) == 0,
        app=app_name,
        namespace=namespace,
        deleted_hpas=deleted_hpas,
        missing_hpas=missing_hpas,
        errors=errors,
    )


def _create_or_replace_cpu_hpa(
    namespace: str,
    deployment_name: str,
    min_replicas: int,
    max_replicas: int,
    average_cpu_utilization: int,
) -> dict[str, Any]:
    autoscaling_api = client.AutoscalingV2Api()
    hpa_name = f"{deployment_name}-hpa"

    body = client.V2HorizontalPodAutoscaler(
        api_version="autoscaling/v2",
        kind="HorizontalPodAutoscaler",
        metadata=client.V1ObjectMeta(name=hpa_name, namespace=namespace),
        spec=client.V2HorizontalPodAutoscalerSpec(
            scale_target_ref=client.V2CrossVersionObjectReference(
                api_version="apps/v1",
                kind="Deployment",
                name=deployment_name,
            ),
            min_replicas=min_replicas,
            max_replicas=max_replicas,
            metrics=[
                client.V2MetricSpec(
                    type="Resource",
                    resource=client.V2ResourceMetricSource(
                        name="cpu",
                        target=client.V2MetricTarget(
                            type="Utilization",
                            average_utilization=average_cpu_utilization,
                        ),
                    ),
                )
            ],
        ),
    )

    try:
        existing = autoscaling_api.read_namespaced_horizontal_pod_autoscaler(name=hpa_name, namespace=namespace)
        body.metadata.resource_version = existing.metadata.resource_version
        autoscaling_api.replace_namespaced_horizontal_pod_autoscaler(name=hpa_name, namespace=namespace, body=body)
        return {
            "deployment": deployment_name,
            "hpa": hpa_name,
            "action": "updated",
            "min_replicas": min_replicas,
            "max_replicas": max_replicas,
            "average_cpu_utilization": average_cpu_utilization,
        }
    except ApiException as exc:
        if exc.status != 404:
            raise

    autoscaling_api.create_namespaced_horizontal_pod_autoscaler(namespace=namespace, body=body)
    return {
        "deployment": deployment_name,
        "hpa": hpa_name,
        "action": "created",
        "min_replicas": min_replicas,
        "max_replicas": max_replicas,
        "average_cpu_utilization": average_cpu_utilization,
    }


def _application_status(
    app_name: str,
    namespace: str,
    deployment_names: list[str],
    service_names: list[str],
) -> dict[str, Any]:
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()

    deployments = [_deployment_status(apps_api, namespace, name) for name in deployment_names]
    services = [_service_status(core_api, namespace, name) for name in service_names]

    return {
        "app": app_name,
        "namespace": namespace,
        "deployments": deployments,
        "services": services,
        "gateway_url_hint": _build_gateway_hint(namespace),
    }


def _delete_application(app_name: str, namespace: str, manifest_paths: list[str]) -> dict[str, Any]:
    deleted_files: list[str] = []
    deleted_resources: list[str] = []
    errors: list[str] = []

    for path_str in manifest_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            resources = _delete_resources_from_yaml(str(path), namespace)
            deleted_files.append(str(path))
            deleted_resources.extend(resources)
        except Exception as exc:
            errors.append(f"{path}: {str(exc)}")

    return {
        "ok": len(errors) == 0,
        "app": app_name,
        "namespace": namespace,
        "deleted_files": deleted_files,
        "deleted_resources": deleted_resources,
        "errors": errors,
    }


def _delete_resources_from_yaml(path: str, default_namespace: str) -> list[str]:
    deleted: list[str] = []

    with open(path, "r", encoding="utf-8") as f:
        docs = list(yaml.safe_load_all(f))

    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()
    autoscaling_api = client.AutoscalingV2Api()

    for doc in docs:
        if not doc:
            continue

        kind = doc.get("kind")
        api_version = doc.get("apiVersion", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", default_namespace)

        if not kind or not name:
            continue

        try:
            if kind == "Deployment":
                apps_api.delete_namespaced_deployment(name=name, namespace=namespace)
            elif kind == "Service":
                core_api.delete_namespaced_service(name=name, namespace=namespace)
            elif kind == "ConfigMap":
                core_api.delete_namespaced_config_map(name=name, namespace=namespace)
            elif kind == "Secret":
                core_api.delete_namespaced_secret(name=name, namespace=namespace)
            elif kind == "ServiceAccount":
                core_api.delete_namespaced_service_account(name=name, namespace=namespace)
            elif kind == "HorizontalPodAutoscaler":
                autoscaling_api.delete_namespaced_horizontal_pod_autoscaler(name=name, namespace=namespace)
            elif kind == "Gateway":
                if api_version.startswith("networking.istio.io/"):
                    custom_api.delete_namespaced_custom_object(
                        group="networking.istio.io",
                        version=api_version.split("/")[1],
                        namespace=namespace,
                        plural="gateways",
                        name=name,
                    )
                elif api_version.startswith("gateway.networking.k8s.io/"):
                    custom_api.delete_namespaced_custom_object(
                        group="gateway.networking.k8s.io",
                        version=api_version.split("/")[1],
                        namespace=namespace,
                        plural="gateways",
                        name=name,
                    )
                else:
                    raise ValueError(f"Unsupported Gateway apiVersion: {api_version}")
            elif kind == "VirtualService":
                custom_api.delete_namespaced_custom_object(
                    group="networking.istio.io",
                    version=api_version.split("/")[1],
                    namespace=namespace,
                    plural="virtualservices",
                    name=name,
                )
            elif kind == "DestinationRule":
                custom_api.delete_namespaced_custom_object(
                    group="networking.istio.io",
                    version=api_version.split("/")[1],
                    namespace=namespace,
                    plural="destinationrules",
                    name=name,
                )
            elif kind == "Namespace":
                core_api.delete_namespace(name=name)
            else:
                continue

            deleted.append(f"{kind}/{name}")
        except ApiException as exc:
            if exc.status == 404:
                deleted.append(f"{kind}/{name} (already absent)")
            else:
                raise

    return deleted


def _monitor_loop(namespace: str, interval: int, prom_url: str, log_file: Path) -> None:
    with log_file.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Timestamp",
            "Scope",
            "Name",
            "HTTP_RPM",
            "HTTP_LAT_ms",
            "gRPC_RPM",
            "gRPC_LAT_ms",
            "CPU_m",
            "MEM_MiB",
            "Pods",
            "CPU_pct",
            "MEM_pct",
            "NET_RX_Bps",
            "NET_TX_Bps",
        ])

        while not _monitor_stop_event.is_set():
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            try:
                services = _get_deployments(namespace)
                for svc in services:
                    http_rpm = _query_prometheus(
                        prom_url,
                        f'sum(rate(istio_requests_total{{request_protocol="http", destination_workload="{svc}"}}[30s])) * 60',
                    )
                    http_lat = _query_prometheus(
                        prom_url,
                        f'sum(rate(istio_request_duration_milliseconds_sum{{request_protocol="http", destination_workload="{svc}"}}[30s])) / '
                        f'sum(rate(istio_request_duration_milliseconds_count{{request_protocol="http", destination_workload="{svc}"}}[30s]))',
                    )
                    grpc_rpm = _query_prometheus(
                        prom_url,
                        f'sum(rate(istio_requests_total{{request_protocol="grpc", destination_workload="{svc}"}}[30s])) * 60',
                    )
                    grpc_lat = _query_prometheus(
                        prom_url,
                        f'sum(rate(istio_request_duration_milliseconds_sum{{request_protocol="grpc", destination_workload="{svc}"}}[30s])) / '
                        f'sum(rate(istio_request_duration_milliseconds_count{{request_protocol="grpc", destination_workload="{svc}"}}[30s]))',
                    )

                    cpu_m, mem_mib, pods = _service_pod_metrics(namespace, svc)

                    writer.writerow([
                        ts,
                        "service",
                        svc,
                        _round1(http_rpm),
                        _round1(http_lat),
                        _round1(grpc_rpm),
                        _round1(grpc_lat),
                        cpu_m,
                        mem_mib,
                        pods,
                        "",
                        "",
                        "",
                        "",
                    ])
                    f.flush()
            except Exception as exc:
                writer.writerow([ts, "service_error", "namespace", str(exc), "", "", "", "", "", "", "", "", "", ""])
                f.flush()

            try:
                nodes = _get_nodes()
                for node in nodes:
                    cpu_m, mem_mib = _node_usage(node)
                    cpu_pct, mem_pct = _node_utilization_percent(node)

                    net_rx_bps = _query_prometheus(
                        prom_url,
                        f'sum(rate(node_network_receive_bytes_total{{instance=~".*{node}.*",device!~"lo|veth.*|cali.*|flannel.*|cni.*"}}[30s]))',
                    )
                    net_tx_bps = _query_prometheus(
                        prom_url,
                        f'sum(rate(node_network_transmit_bytes_total{{instance=~".*{node}.*",device!~"lo|veth.*|cali.*|flannel.*|cni.*"}}[30s]))',
                    )

                    writer.writerow([
                        ts,
                        "node",
                        node,
                        "",
                        "",
                        "",
                        "",
                        cpu_m,
                        mem_mib,
                        "",
                        _round1(cpu_pct),
                        _round1(mem_pct),
                        _round1(net_rx_bps),
                        _round1(net_tx_bps),
                    ])
                    f.flush()
            except Exception as exc:
                writer.writerow([ts, "node_error", "cluster", str(exc), "", "", "", "", "", "", "", "", "", ""])
                f.flush()

            _monitor_stop_event.wait(interval)

    _monitor_state["running"] = False


def _get_deployments(namespace: str) -> list[str]:
    apps_api = client.AppsV1Api()
    resp = apps_api.list_namespaced_deployment(namespace=namespace)
    names = [item.metadata.name for item in resp.items if item.metadata and item.metadata.name]
    return [name for name in names if name in BOOKINFO_DEPLOYMENTS]


def _get_nodes() -> list[str]:
    core_api = client.CoreV1Api()
    resp = core_api.list_node()
    return [item.metadata.name for item in resp.items if item.metadata and item.metadata.name]


def _service_pod_metrics(namespace: str, deployment_name: str) -> tuple[int, int, int]:
    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()

    cpu_m = 0
    mem_mib = 0
    running_pods = 0

    try:
        dep = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        match_labels = dep.spec.selector.match_labels or {}
    except Exception:
        return 0, 0, 0

    label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())
    if not label_selector:
        return 0, 0, 0

    try:
        pod_list = core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        matched_pods = {pod.metadata.name for pod in pod_list.items if pod.metadata and pod.metadata.name}
        running_pods = sum(1 for pod in pod_list.items if (pod.status.phase or "") == "Running")
    except Exception:
        return 0, 0, 0

    try:
        metrics = custom_api.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods",
        )
    except Exception:
        return 0, 0, running_pods

    for item in metrics.get("items", []):
        pod_name = item.get("metadata", {}).get("name", "")
        if pod_name not in matched_pods:
            continue

        for container_metrics in item.get("containers", []):
            usage = container_metrics.get("usage", {})
            cpu_m += _parse_cpu_to_millicores(usage.get("cpu", "0"))
            mem_mib += _parse_memory_to_mib(usage.get("memory", "0Ki"))

    return cpu_m, mem_mib, running_pods


def _node_usage(node_name: str) -> tuple[int, int]:
    custom_api = client.CustomObjectsApi()

    try:
        metric = custom_api.get_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
            name=node_name,
        )
    except Exception:
        return 0, 0

    usage = metric.get("usage", {})
    cpu_m = _parse_cpu_to_millicores(usage.get("cpu", "0"))
    mem_mib = _parse_memory_to_mib(usage.get("memory", "0Ki"))
    return cpu_m, mem_mib


def _node_utilization_percent(node_name: str) -> tuple[float, float]:
    core_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()

    try:
        node_obj = core_api.read_node(name=node_name)
        alloc_cpu_m = _parse_cpu_to_millicores(node_obj.status.allocatable.get("cpu", "0"))
        alloc_mem_mib = _parse_memory_to_mib(node_obj.status.allocatable.get("memory", "0Ki"))
    except Exception:
        return 0.0, 0.0

    try:
        metric = custom_api.get_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
            name=node_name,
        )
        usage = metric.get("usage", {})
        used_cpu_m = _parse_cpu_to_millicores(usage.get("cpu", "0"))
        used_mem_mib = _parse_memory_to_mib(usage.get("memory", "0Ki"))
    except Exception:
        return 0.0, 0.0

    cpu_pct = (used_cpu_m / alloc_cpu_m * 100.0) if alloc_cpu_m > 0 else 0.0
    mem_pct = (used_mem_mib / alloc_mem_mib * 100.0) if alloc_mem_mib > 0 else 0.0
    return cpu_pct, mem_pct


def _query_prometheus(prom_url: str, query: str) -> float:
    try:
        resp = requests.get(prom_url, params={"query": query}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("data", {}).get("result", [])
        if not result:
            return 0.0
        value = float(result[0].get("value", [None, "0"])[1])
        if math.isnan(value) or math.isinf(value):
            return 0.0
        return value
    except Exception:
        return 0.0


def _parse_cpu_to_millicores(value: str) -> int:
    if not value:
        return 0
    try:
        if value.endswith("n"):
            return int(float(value[:-1]) / 1_000_000)
        if value.endswith("u"):
            return int(float(value[:-1]) / 1_000)
        if value.endswith("m"):
            return int(float(value[:-1]))
        return int(float(value) * 1000)
    except ValueError:
        return 0


def _parse_memory_to_mib(value: str) -> int:
    if not value:
        return 0

    binary_units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
        "Pi": 1024 * 1024 * 1024,
        "Ei": 1024 * 1024 * 1024 * 1024,
    }
    decimal_units = {
        "K": 1000 / (1024 * 1024),
        "M": 1000 * 1000 / (1024 * 1024),
        "G": 1000 * 1000 * 1000 / (1024 * 1024),
        "T": 1000 * 1000 * 1000 * 1000 / (1024 * 1024),
    }

    try:
        for unit, factor in binary_units.items():
            if value.endswith(unit):
                return int(float(value[:-len(unit)]) * factor)
        for unit, factor in decimal_units.items():
            if value.endswith(unit):
                return int(float(value[:-len(unit)]) * factor)
        return int(float(value) / (1024 * 1024))
    except ValueError:
        return 0


def _round1(value: float | int | None) -> str:
    if value in (None, 0, 0.0):
        return "0.0"
    try:
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return "0.0"
        return f"{v:.1f}"
    except (TypeError, ValueError):
        return "0.0"


def _ensure_namespace(core_api: client.CoreV1Api, namespace: str) -> None:
    try:
        core_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            core_api.create_namespace(body=client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace)))
            return
        raise


def _ensure_deployment_exists(apps_api: client.AppsV1Api, namespace: str, deployment_name: str) -> None:
    try:
        apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise HTTPException(
                status_code=404,
                detail=f"Deployment not found: {deployment_name} in namespace {namespace}",
            ) from exc
        raise


def _apply_yaml(api_client: ApiClient, path: str, namespace: str) -> None:
    utils.create_from_yaml(api_client, path, namespace=namespace, verbose=False)


def _format_fail_to_create(exc: utils.FailToCreateError) -> str:
    return "; ".join(str(e) for e in exc.api_exceptions)


def _build_gateway_hint(namespace: str) -> str:
    return f"Check ingress or gateway exposure for namespace '{namespace}'"


def _deployment_status(apps_api: client.AppsV1Api, namespace: str, name: str) -> dict[str, Any]:
    try:
        dep = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
        status = dep.status
        return {
            "name": name,
            "exists": True,
            "replicas": dep.spec.replicas or 0,
            "ready_replicas": status.ready_replicas or 0,
            "available_replicas": status.available_replicas or 0,
        }
    except ApiException as exc:
        if exc.status == 404:
            return {"name": name, "exists": False}
        raise


def _service_status(core_api: client.CoreV1Api, namespace: str, name: str) -> dict[str, Any]:
    try:
        svc = core_api.read_namespaced_service(name=name, namespace=namespace)
        return {
            "name": name,
            "exists": True,
            "type": svc.spec.type,
            "cluster_ip": svc.spec.cluster_ip,
            "ports": [{"port": p.port, "target_port": p.target_port} for p in (svc.spec.ports or [])],
        }
    except ApiException as exc:
        if exc.status == 404:
            return {"name": name, "exists": False}
        raise
