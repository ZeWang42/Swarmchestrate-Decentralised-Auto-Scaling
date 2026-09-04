from __future__ import annotations

import time
from typing import Any

from fastapi import HTTPException
from kubernetes import client

from config import APPLICATIONS
from experiment.models import (
    DeployAutoscalerRequest,
    ExperimentCleanupRequest,
    ExperimentSetupRequest,
    ExperimentSetupResponse,
    StartMonitorRequest,
)
from experiment.monitor_logic import start_monitor_logic, stop_monitor_logic
from k8s.hpa_ops import deploy_autoscaler_for_application, delete_autoscaler_for_application, discover_app_deployments, normalize_autoscaler_name


def _get_app_deployments(app_name: str) -> list[str]:
    app_key = app_name.strip().lower()
    cfg = APPLICATIONS.get(app_key)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"Unsupported app: {app_name}. Supported apps: {sorted(APPLICATIONS)}")
    return cfg["deployments"]


def prepare_initial_state(app_name: str, namespace: str, autoscaler_name: str, autoscaler_deployments: list[str] | None) -> None:
    app_deployments = _get_app_deployments(app_name)

    try:
        delete_autoscaler_for_application(app_name, namespace, autoscaler_name, autoscaler_deployments)
    except Exception:
        pass

    apps_api = client.AppsV1Api()
    for dep in app_deployments:
        try:
            apps_api.patch_namespaced_deployment_scale(name=dep, namespace=namespace, body={"spec": {"replicas": 1}})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to scale {dep}: {str(exc)}")

    timeout = 60
    start = time.time()
    while True:
        all_ready = True
        for dep in app_deployments:
            d = apps_api.read_namespaced_deployment(dep, namespace)
            ready = d.status.ready_replicas or 0
            if ready != 1:
                all_ready = False
                break
        if all_ready:
            break
        if time.time() - start > timeout:
            raise HTTPException(status_code=500, detail=f"Timeout waiting for {app_name} deployments to scale to 1")
        time.sleep(2)


def setup_experiment_logic(req: ExperimentSetupRequest) -> ExperimentSetupResponse:
    app_name = req.app.strip().lower()
    _get_app_deployments(app_name)

    autoscaler_result: dict[str, Any] | None = None
    autoscaler_name = normalize_autoscaler_name(req.autoscaler.autoscaler_name)
    target_deployments = discover_app_deployments(app_name, req.namespace, req.autoscaler.deployment_names)

    prepare_initial_state(app_name, req.namespace, autoscaler_name, target_deployments)

    if autoscaler_name != "none":
        autoscaler_resp = deploy_autoscaler_for_application(
            app_name,
            DeployAutoscalerRequest(
                namespace=req.namespace,
                deployment_names=target_deployments,
                autoscaler_name=autoscaler_name,
                config=req.autoscaler.config,
            ),
        )
        autoscaler_result = autoscaler_resp.model_dump()

    monitor_resp = start_monitor_logic(
        StartMonitorRequest(
            namespace=req.namespace,
            interval=req.monitor.interval,
            prom_url=req.monitor.prom_url,
            file_prefix=f"{req.monitor.file_prefix}_{app_name}_{req.workload_name or 'workload'}_{autoscaler_name}",
            autoscaler_name=autoscaler_name,
            latency_percentile=req.monitor.latency_percentile,
        )
    )

    return ExperimentSetupResponse(
        ok=True,
        app=app_name,
        namespace=req.namespace,
        workload_name=req.workload_name,
        duration_seconds=req.duration_seconds,
        autoscaler_name=autoscaler_name,
        autoscaler_result=autoscaler_result,
        monitor_result=monitor_resp.model_dump(),
        ready_for_load=True,
    )


def cleanup_experiment_logic(req: ExperimentCleanupRequest) -> dict[str, Any]:
    app_name = req.app.strip().lower()
    app_deployments = _get_app_deployments(app_name)

    result: dict[str, Any] = {
        "ok": True,
        "app": app_name,
        "namespace": req.namespace,
        "monitor_stopped": None,
        "autoscaler_deleted": None,
        "errors": [],
    }

    if req.stop_monitoring:
        try:
            result["monitor_stopped"] = stop_monitor_logic().model_dump()
        except Exception as exc:
            result["errors"].append(f"monitor stop failed: {str(exc)}")

    if req.delete_autoscaler:
        try:
            autoscaler_deleted = delete_autoscaler_for_application(
                app_name,
                req.namespace,
                req.autoscaler_name,
                req.deployment_names,
            ).model_dump()
            result["autoscaler_deleted"] = autoscaler_deleted
            if not autoscaler_deleted.get("ok", False):
                delete_errors = autoscaler_deleted.get("errors") or ["unknown autoscaler deletion error"]
                result["errors"].extend(
                    f"autoscaler delete failed: {error}"
                    for error in delete_errors
                )
        except Exception as exc:
            result["errors"].append(f"autoscaler delete failed: {str(exc)}")

    apps_api = client.AppsV1Api()
    for dep in app_deployments:
        try:
            apps_api.patch_namespaced_deployment_scale(name=dep, namespace=req.namespace, body={"spec": {"replicas": 1}})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to scale {dep}: {str(exc)}")

    result["ok"] = len(result["errors"]) == 0
    return result
