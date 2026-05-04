from __future__ import annotations

from pathlib import Path
import time
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from kubernetes import client
from kubernetes.client.exceptions import ApiException

from config import (
    APPLICATIONS,
    AUTOSCALER_MANIFESTS_DIR,
    AUTOSCALER_NAME_ALIASES,
    PROM_URL,
)
from experiment.models import DeployAutoscalerRequest, DeployAutoscalerResponse, DeleteAutoscalerResponse
from k8s.app_ops import ensure_deployment_exists
from k8s.resource_ops import apply_objects
from utils.templating import render_template


ALLOWED_APP_DEPLOYMENTS = {
    app_name: app_cfg["deployments"]
    for app_name, app_cfg in APPLICATIONS.items()
}


SHARED_PREFIX = "shared-"
PER_DEPLOYMENT_PREFIX = "per-deployment-"
FALLBACK_FILENAMES = {"manifest.yaml", "manifest.yml"}



def wait_for_deployments(
    namespace: str,
    deployment_names: list[str],
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 2,
) -> None:
    apps_api = client.AppsV1Api()
    deadline = time.time() + timeout_seconds
    pending = set(deployment_names)

    while time.time() < deadline:
        still_pending: set[str] = set()

        for name in pending:
            try:
                dep = apps_api.read_namespaced_deployment(name=name, namespace=namespace)
            except ApiException as exc:
                if exc.status == 404:
                    still_pending.add(name)
                    continue
                raise

            desired = dep.spec.replicas or 0
            ready = dep.status.ready_replicas or 0
            updated = dep.status.updated_replicas or 0
            available = dep.status.available_replicas or 0

            if not (
                desired > 0
                and ready >= desired
                and updated >= desired
                and available >= desired
            ):
                still_pending.add(name)

        if not still_pending:
            return

        pending = still_pending
        time.sleep(poll_interval_seconds)

    raise TimeoutError(
        f"Timed out waiting for deployments in namespace '{namespace}' to become ready: "
        f"{sorted(pending)}"
    )
def normalize_autoscaler_name(name: str) -> str:
    normalized = name.strip().lower().replace("-", "_")
    return AUTOSCALER_NAME_ALIASES.get(normalized, normalized)


def _autoscaler_dir(autoscaler_name: str) -> Path:
    path = AUTOSCALER_MANIFESTS_DIR / autoscaler_name
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Unsupported autoscaler: {autoscaler_name}")
    return path


def _sorted_template_files(path: Path, prefix: str) -> list[Path]:
    return sorted(
        p for p in path.iterdir()
        if p.is_file() and p.suffix in {".yaml", ".yml"} and p.name.startswith(prefix)
    )


def _fallback_template_files(path: Path) -> list[Path]:
    return sorted(
        p for p in path.iterdir()
        if p.is_file() and p.suffix in {".yaml", ".yml"} and p.name in FALLBACK_FILENAMES
    )


def discover_app_deployments(app_name: str, namespace: str, requested: list[str] | None = None) -> list[str]:
    apps_api = client.AppsV1Api()
    allowed = ALLOWED_APP_DEPLOYMENTS.get(app_name)
    if not allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported app: {app_name}")

    if requested:
        deployment_names = requested
    else:
        deployment_names = []
        for deployment_name in allowed:
            try:
                apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
                deployment_names.append(deployment_name)
            except ApiException as exc:
                if exc.status == 404:
                    continue
                raise

    if not deployment_names:
        raise HTTPException(status_code=404, detail=f"No matching deployments found for app {app_name} in namespace {namespace}")

    for deployment_name in deployment_names:
        ensure_deployment_exists(apps_api, namespace, deployment_name)

    return deployment_names


def _build_context(req: DeployAutoscalerRequest, deployment_name: str | None = None, app_name: str | None = None) -> dict[str, Any]:
    cfg = req.config or {}
    context: dict[str, Any] = {
        "namespace": req.namespace,
        "target_namespace": req.namespace,
        "autoscaler_name": req.autoscaler_name,
        "service_account_name": cfg.get("service_account_name", "das-autoscaler"),
        "image": cfg.get("image", "busybox:stable"),
        "prom_url": cfg.get("prom_url", PROM_URL),
        "interval": cfg.get("interval", 15),
        "cooldown_seconds": cfg.get("cooldown_seconds", 30),
        "alpha_down_threshold": cfg.get("alpha_down_threshold", 30),
        "tau_min": cfg.get("tau_min", 60),
        "tau_max": cfg.get("tau_max", 80),
        "beta_up_threshold": cfg.get("beta_up_threshold", 90),
        "min_replicas": cfg.get("min_replicas", 1),
        "max_replicas": cfg.get("max_replicas", 10),
        "average_cpu_utilization": cfg.get("average_cpu_utilization", cfg.get("cpu_target", 70)),
    }
    if deployment_name is not None:
        safe_name = deployment_name.replace("_", "-").replace(".", "-")
        context.update({
            "deployment_name": deployment_name,
            "target_deployment": deployment_name,
            "controller_name": f"{req.autoscaler_name}-autoscaler-{safe_name}",
            "autoscaler_deployment_name": f"{req.autoscaler_name}-autoscaler-{safe_name}",
        })
        prefix = req.autoscaler_name
        if req.autoscaler_name in {"das", "customdas"}:
            context["autoscaler_deployment_name"] = f"{prefix}-autoscaler-{safe_name}"
            context["controller_name"] = context["autoscaler_deployment_name"]
            context["autoscaler_name"] = context["autoscaler_deployment_name"]

        # CustomDAS templates need peer-to-peer variables for every per-deployment
        # controller. The client may provide p2p_hub_deployment, but older clients
        # do not provide peer_id, p2p_hub_host, or is_p2p_hub. Fill safe defaults
        # here so setup and cleanup can render the same templates.
        if req.autoscaler_name == "customdas":
            app_deployments = APPLICATIONS.get(app_name or "", {}).get("deployments", [])
            default_hub_deployment = app_deployments[0] if app_deployments else deployment_name
            hub_deployment = cfg.get("p2p_hub_deployment", default_hub_deployment)
            hub_safe_name = str(hub_deployment).replace("_", "-").replace(".", "-")
            hub_controller_name = f"customdas-autoscaler-{hub_safe_name}"
            p2p_hub_port = cfg.get("p2p_hub_port", 5000)

            context.update({
                "peer_id": cfg.get("peer_id", deployment_name),
                "p2p_hub_deployment": hub_deployment,
                "p2p_hub_host": cfg.get(
                    "p2p_hub_host",
                    f"{hub_controller_name}.{req.namespace}.svc.cluster.local",
                ),
                "p2p_hub_port": p2p_hub_port,
                "is_p2p_hub": str(deployment_name == hub_deployment).lower(),
            })
    return context


def _render_autoscaler_objects(req: DeployAutoscalerRequest, deployment_names: list[str], app_name: str | None = None) -> list[dict[str, Any]]:
    autoscaler_dir = _autoscaler_dir(req.autoscaler_name)
    all_objects: list[dict[str, Any]] = []

    for template_path in _sorted_template_files(autoscaler_dir, SHARED_PREFIX):
        all_objects.extend(render_template(template_path, _build_context(req, app_name=app_name)))

    per_deployment_templates = _sorted_template_files(autoscaler_dir, PER_DEPLOYMENT_PREFIX)
    if not per_deployment_templates:
        per_deployment_templates = _fallback_template_files(autoscaler_dir)

    for deployment_name in deployment_names:
        ctx = _build_context(req, deployment_name, app_name=app_name)
        for template_path in per_deployment_templates:
            all_objects.extend(render_template(template_path, ctx))

    return all_objects


def deploy_autoscaler_for_application(app_name: str, req: DeployAutoscalerRequest) -> DeployAutoscalerResponse:
    namespace = req.namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace must not be empty")

    req.autoscaler_name = normalize_autoscaler_name(req.autoscaler_name)
    if req.autoscaler_name == "none":
        return DeployAutoscalerResponse(ok=True, app=app_name, namespace=namespace, autoscaler_name=req.autoscaler_name, results=[])

    deployment_names = discover_app_deployments(app_name, namespace, req.deployment_names)
    req.deployment_names = deployment_names
    results: list[dict[str, Any]] = []

    # check to ensure hpa is deployed
    try:
        objs = _render_autoscaler_objects(req, deployment_names, app_name)
        apply_objects(objs, namespace)

#        if req.autoscaler_name == "das":
#            controller_names = [
#                f"das-autoscaler-{d.replace('_', '-').replace('.', '-')}"
#                for d in deployment_names
#            ]
        if req.autoscaler_name in {"das", "customdas"}:
            controller_names = [
                f"{req.autoscaler_name}-autoscaler-{d.replace('_', '-').replace('.', '-')}"
                for d in deployment_names
            ]
            wait_for_deployments(namespace, controller_names)

        for deployment_name in deployment_names:
            result: dict[str, Any] = {
                "deployment": deployment_name,
                "autoscaler": req.autoscaler_name,
                "action": "applied",
            }
#            if req.autoscaler_name == "das":
#                safe_name = deployment_name.replace("_", "-").replace(".", "-")
#                result["controller_name"] = f"das-autoscaler-{safe_name}"
            if req.autoscaler_name in {"das", "customdas"}:
                safe_name = deployment_name.replace("_", "-").replace(".", "-")
                result["controller_name"] = f"{req.autoscaler_name}-autoscaler-{safe_name}"
            results.append(result)
        return DeployAutoscalerResponse(ok=True, app=app_name, namespace=namespace, autoscaler_name=req.autoscaler_name, results=results)        
    # try:
    #     objs = _render_autoscaler_objects(req, deployment_names, app_name)
    #     apply_objects(objs, namespace)
    #     # check if all expected deployments are created and running before returning success
    #     # sleep 10 seconds


    #     for deployment_name in deployment_names:
    #         result: dict[str, Any] = {
    #             "deployment": deployment_name,
    #             "autoscaler": req.autoscaler_name,
    #             "action": "applied",
    #         }
    #         if req.autoscaler_name == "das":
    #             safe_name = deployment_name.replace("_", "-").replace(".", "-")
    #             result["controller_name"] = f"das-autoscaler-{safe_name}"
    #         results.append(result)
    #    return DeployAutoscalerResponse(ok=True, app=app_name, namespace=namespace, autoscaler_name=req.autoscaler_name, results=results)
    except ApiException as exc:
        raise HTTPException(status_code=exc.status or 500, detail=exc.body or str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_DELETE_MAP: dict[str, tuple[str, str, str]] = {
    "ServiceAccount": ("core", "namespaced", "service_account"),
    "Role": ("rbac", "namespaced", "role"),
    "RoleBinding": ("rbac", "namespaced", "role_binding"),
    "Deployment": ("apps", "namespaced", "deployment"),
    "HorizontalPodAutoscaler": ("autoscaling", "namespaced", "horizontal_pod_autoscaler"),
}


def _delete_rendered_object(obj: dict[str, Any], default_namespace: str) -> tuple[str, str]:
    kind = obj.get("kind")
    metadata = obj.get("metadata", {})
    name = metadata.get("name")
    namespace = metadata.get("namespace") or default_namespace
    if not kind or not name:
        raise ValueError("Rendered object must define kind and metadata.name")

    api_name, scope, resource_name = _DELETE_MAP.get(kind, (None, None, None))
    if api_name is None:
        return ("ignored", f"{kind}/{name}")

    api = {
        "core": client.CoreV1Api(),
        "rbac": client.RbacAuthorizationV1Api(),
        "apps": client.AppsV1Api(),
        "autoscaling": client.AutoscalingV2Api(),
    }[api_name]
    method = getattr(api, f"delete_{scope}_{resource_name}")
    method(name=name, namespace=namespace)
    return ("deleted", f"{kind}/{name}")


def delete_autoscaler_for_application(app_name: str, namespace: str, autoscaler_name: str, deployment_names: list[str] | None) -> DeleteAutoscalerResponse:
    namespace = namespace.strip()
    if not namespace:
        raise HTTPException(status_code=400, detail="Namespace must not be empty")

    autoscaler_name = normalize_autoscaler_name(autoscaler_name)
    deleted_resources: list[str] = []
    missing_resources: list[str] = []
    errors: list[str] = []

    if autoscaler_name == "none":
        return DeleteAutoscalerResponse(
            ok=True,
            app=app_name,
            namespace=namespace,
            autoscaler_name=autoscaler_name,
            deleted_resources=[],
            missing_resources=[],
            errors=[],
        )

    try:
        resolved_deployments = discover_app_deployments(app_name, namespace, deployment_names)
        req = DeployAutoscalerRequest(
            namespace=namespace,
            deployment_names=resolved_deployments,
            autoscaler_name=autoscaler_name,
            config={},
        )
        objects = _render_autoscaler_objects(req, resolved_deployments, app_name)
        seen: set[tuple[str, str, str]] = set()
        for obj in objects:
            kind = obj.get("kind")
            metadata = obj.get("metadata", {})
            obj_namespace = metadata.get("namespace") or namespace
            name = metadata.get("name")
            if not kind or not name:
                continue
            key = (kind, obj_namespace, name)
            if key in seen:
                continue
            seen.add(key)
            try:
                status, label = _delete_rendered_object(obj, namespace)
                if status == "deleted":
                    deleted_resources.append(label)
            except ApiException as exc:
                if exc.status == 404:
                    missing_resources.append(f"{kind}/{name}")
                else:
                    errors.append(f"{kind}/{name}: {exc.body or str(exc)}")
    except HTTPException:
        raise
    except KeyError as exc:
        errors.append(str(exc))
    except Exception as exc:
        errors.append(str(exc))

    return DeleteAutoscalerResponse(
        ok=len(errors) == 0,
        app=app_name,
        namespace=namespace,
        autoscaler_name=autoscaler_name,
        deleted_resources=deleted_resources,
        missing_resources=missing_resources,
        errors=errors,
    )
