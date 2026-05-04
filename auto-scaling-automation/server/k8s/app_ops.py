
from __future__ import annotations

from pathlib import Path
from typing import Any
from fastapi import HTTPException
from kubernetes import client, utils
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException

from experiment.models import DeployAppRequest, DeployAppResponse
from k8s.resource_ops import apply_yaml, delete_resources_from_yaml
from utils.formatting import build_gateway_hint, format_fail_to_create

def ensure_namespace(core_api: client.CoreV1Api, namespace: str) -> None:
    try:
        core_api.read_namespace(name=namespace)
    except ApiException as exc:
        if exc.status == 404:
            core_api.create_namespace(body=client.V1Namespace(metadata=client.V1ObjectMeta(name=namespace)))
            return
        raise

def ensure_deployment_exists(apps_api: client.AppsV1Api, namespace: str, deployment_name: str) -> None:
    try:
        apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            raise HTTPException(status_code=404, detail=f"Deployment not found: {deployment_name} in namespace {namespace}") from exc
        raise

def deploy_application(app_name: str, req: DeployAppRequest) -> DeployAppResponse:
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
    if req.create_namespace and namespace != "default":
        ensure_namespace(core_api, namespace)

    applied_files: list[str] = []
    try:
        apply_yaml(str(manifest), namespace)
        applied_files.append(str(manifest))
        if gateway_manifest is not None:
            apply_yaml(str(gateway_manifest), namespace)
            applied_files.append(str(gateway_manifest))

        return DeployAppResponse(
            ok=True,
            message=f"{app_name} deployment submitted successfully",
            app=app_name,
            namespace=namespace,
            applied_files=applied_files,
            gateway_url_hint=build_gateway_hint(namespace),
        )
    except utils.FailToCreateError as exc:
        raise HTTPException(status_code=500, detail=format_fail_to_create(exc)) from exc
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=exc.body or str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

def delete_application(app_name: str, namespace: str, manifest_paths: list[str]) -> dict[str, Any]:
    deleted_files: list[str] = []
    deleted_resources: list[str] = []
    errors: list[str] = []

    for path_str in manifest_paths:
        path = Path(path_str)
        if not path.exists():
            continue
        try:
            resources = delete_resources_from_yaml(str(path), namespace)
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

def deployment_status(apps_api: client.AppsV1Api, namespace: str, name: str) -> dict[str, Any]:
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

def service_status(core_api: client.CoreV1Api, namespace: str, name: str) -> dict[str, Any]:
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

def application_status(app_name: str, namespace: str, deployment_names: list[str], service_names: list[str]) -> dict[str, Any]:
    apps_api = client.AppsV1Api()
    core_api = client.CoreV1Api()
    return {
        "app": app_name,
        "namespace": namespace,
        "deployments": [deployment_status(apps_api, namespace, name) for name in deployment_names],
        "services": [service_status(core_api, namespace, name) for name in service_names],
        "gateway_url_hint": build_gateway_hint(namespace),
    }
