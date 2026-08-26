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
CONTROLLER_DEPLOYMENT_AUTOSCALERS = {"das", "customdas", "customdas-cpu", "customdas-cpu-queue", "dadqn"}
SHARED_DEPLOYMENT_AUTOSCALERS = {"pbscaler": ["pbscaler-boutique"], "hab": ["hab-autoscaler-onlineboutique"]}
COMPANION_SERVICE_AUTOSCALERS = {"das", "customdas", "customdas-cpu", "customdas-cpu-queue"}
DADQN_APP_NAME = "onlineboutique"
DADQN_UNSUPPORTED_DEPLOYMENTS = {"redis-cart"}
CUSTOMDAS_FAMILY_AUTOSCALERS = {"customdas", "customdas-cpu", "customdas-cpu-queue"}
HAB_APP_NAME = "onlineboutique"
HAB_UNSUPPORTED_DEPLOYMENTS = {"redis-cart"}


def _safe_k8s_name(name: str) -> str:
    return name.replace("_", "-").replace(".", "-")


def _controller_name_for(autoscaler_name: str, deployment_name: str) -> str:
    safe_name = _safe_k8s_name(deployment_name)
    if autoscaler_name == "dadqn":
        # Match the DA-DQN upstream convention: dadqn-frontend, dadqn-cartservice, ...
        return f"dadqn-{safe_name}"
    return f"{autoscaler_name}-autoscaler-{safe_name}"



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


def _validate_and_filter_dadqn_deployments(
    app_name: str,
    requested: list[str] | None,
    deployment_names: list[str],
) -> list[str]:
    """DA-DQN upstream models/manifests target Online Boutique services only.

    The upstream project ships one agent/model per Online Boutique microservice
    and does not include a redis-cart agent. When deployment_names is omitted,
    silently filter redis-cart out. When explicitly requested, fail fast so the
    caller knows the agent/model is not available.
    """
    if app_name != DADQN_APP_NAME:
        raise HTTPException(
            status_code=400,
            detail="DA-DQN autoscaler is supported only for app='onlineboutique'.",
        )

    unsupported = sorted(set(deployment_names) & DADQN_UNSUPPORTED_DEPLOYMENTS)
    if unsupported and requested:
        raise HTTPException(
            status_code=400,
            detail=f"DA-DQN has no bundled agent/model for deployments: {unsupported}",
        )

    return [d for d in deployment_names if d not in DADQN_UNSUPPORTED_DEPLOYMENTS]




def _validate_and_filter_hab_deployments(
    app_name: str,
    requested: list[str] | None,
    deployment_names: list[str],
) -> list[str]:
    """HAB scheduler is a single Online Boutique application-level controller.

    The runtime p-vector excludes redis-cart because it is stateful and not part
    of the calibrated HAB Online Boutique service vector.
    """
    if app_name != HAB_APP_NAME:
        raise HTTPException(
            status_code=400,
            detail="HAB autoscaler is supported only for app='onlineboutique'.",
        )

    unsupported = sorted(set(deployment_names) & HAB_UNSUPPORTED_DEPLOYMENTS)
    if unsupported and requested:
        raise HTTPException(
            status_code=400,
            detail=f"HAB does not manage deployments: {unsupported}",
        )

    return [d for d in deployment_names if d not in HAB_UNSUPPORTED_DEPLOYMENTS]


def _build_context(req: DeployAutoscalerRequest, deployment_name: str | None = None, app_name: str | None = None) -> dict[str, Any]:
    cfg = req.config or {}
    default_image = "busybox:stable"
    default_service_account = "das-autoscaler"
    if req.autoscaler_name == "dadqn":
        default_image = "proactivellmbasedproject/dadqn-autoscaler:v4-decentralized"
        default_service_account = "dadqn-autoscaler"
    elif req.autoscaler_name == "customdas-cpu":
        default_image = "zewang42/customdas-autoscaler-cpu:latest"
        default_service_account = "das-autoscaler"
    elif req.autoscaler_name == "customdas-cpu-queue":
        default_image = "zewang42/customdas-autoscaler-cpu-queue:latest"
        default_service_account = "das-autoscaler"
    elif req.autoscaler_name == "pbscaler":
        default_image = "proactivellmbasedproject/pbscaler-boutique:latest"
        default_service_account = "default"
    elif req.autoscaler_name == "hab":
        default_image = "zewang42/hab-autoscaler"
        default_service_account = "das-autoscaler"

    prom_base_url = cfg.get(
        "prometheus_url",
        cfg.get("prom_url_base", str(PROM_URL).removesuffix("/api/v1/query")),
    )

    app_cfg = APPLICATIONS.get(app_name or "", {})
    resolved_app_name = cfg.get("app_name", app_name or app_cfg.get("name", ""))
    root_service = cfg.get(
        "root_service",
        cfg.get("p2p_hub_deployment", app_cfg.get("latency_deployment", "frontend")),
    )

    # Start with the complete client-provided autoscaler config so templates
    # can consume new parameters without requiring a server code change.
    # Known/resolved server fields below intentionally override conflicting
    # config keys (for example namespace and deployment_name).
    context: dict[str, Any] = dict(cfg)
    context.update({
        "namespace": req.namespace,
        "target_namespace": req.namespace,
        "autoscaler_name": req.autoscaler_name,
        "app_name": resolved_app_name,
        "root_service": root_service,
        "service_account_name": cfg.get("service_account_name", default_service_account),
        "image": cfg.get("image", default_image),
        "image_pull_policy": cfg.get("image_pull_policy", "IfNotPresent" if req.autoscaler_name == "dadqn" else "Always"),
        "prom_url": cfg.get("prom_url", PROM_URL),
        "prometheus_url": prom_base_url,
        "prom_rate_window": cfg.get("prom_rate_window", "1m"),
        "sample_interval_sec": cfg.get("sample_interval_sec", 30),
        "decision_interval_sec": cfg.get("decision_interval_sec", 15),
        "scale_down_cooldown_sec": cfg.get("scale_down_cooldown_sec", 30),
        "obs_fallback_from_cpu": cfg.get("obs_fallback_from_cpu", 1),
        "locust_url": cfg.get("locust_url", ""),
        "model_dir": cfg.get("model_dir", "/mnt/sla_v1"),
        "model_host_path": cfg.get("model_host_path", "/tmp/sla_v1"),
        "interval": cfg.get("interval", 15),
        "cooldown_seconds": cfg.get("cooldown_seconds", 30),
        "alpha_down_threshold": cfg.get("alpha_down_threshold", 30),
        "tau_min": cfg.get("tau_min", 60),
        "tau_max": cfg.get("tau_max", 80),
        "beta_up_threshold": cfg.get("beta_up_threshold", 90),
        "min_replicas": cfg.get("min_replicas", 1),
        "max_replicas": cfg.get("max_replicas", 10),
        "slo_ms": cfg.get("slo_ms", cfg.get("latency_slo_ms", cfg.get("slo_latency_ms", 400))),
        "slo_leaf_ms": cfg.get("slo_leaf_ms", cfg.get("latency_slo_ms_leaf", cfg.get("latency_slo_leaf_ms", 10))),
        "slo_latency_percentile": cfg.get("slo_latency_percentile", "p95"),
        "queue_model_percentile": cfg.get("queue_model_percentile", cfg.get("slo_latency_percentile", "p95")),
        "log_file": cfg.get("log_file", cfg.get("LOG_FILE", "/tmp/customdas.log")),
        "enable_coloured_logs": str(
            cfg.get("enable_coloured_logs", cfg.get("ENABLE_COLOURED_LOGS", 1))
        ).lower(),
        "latency_slo_mode": cfg.get("latency_slo_mode", cfg.get("LATENCY_SLO_MODE", "adaptive")),
        "queue_model": cfg.get("queue_model", cfg.get("QUEUE_MODEL", "mmc")),
        "service_time_update_interval_seconds": cfg.get(
            "service_time_update_interval_seconds",
            cfg.get("SERVICE_TIME_UPDATE_INTERVAL_SECONDS", 29),
        ),
        "service_time_ewma_alpha": cfg.get(
            "service_time_ewma_alpha",
            cfg.get("SERVICE_TIME_EWMA_ALPHA", 0.8),
        ),
        "min_processing_time_ms": cfg.get(
            "min_processing_time_ms",
            cfg.get("MIN_PROCESSING_TIME_MS", 1),
        ),
        "ggc_initial_k": cfg.get("ggc_initial_k", cfg.get("GGC_INITIAL_K", 1.0)),
        "ggc_k_update_interval_seconds": cfg.get(
            "ggc_k_update_interval_seconds",
            cfg.get("GGC_K_UPDATE_INTERVAL_SECONDS", 180),
        ),
        "ggc_k_ewma_alpha": cfg.get("ggc_k_ewma_alpha", cfg.get("GGC_K_EWMA_ALPHA", 0.8)),
        "ggc_k_min": cfg.get("ggc_k_min", cfg.get("GGC_K_MIN", 0.5)),
        "ggc_k_max": cfg.get("ggc_k_max", cfg.get("GGC_K_MAX", 10.0)),
        "frontend_healthy_latency_ms": cfg.get(
            "frontend_healthy_latency_ms",
            cfg.get("FRONTEND_HEALTHY_LATENCY_MS", 500),
        ),
        "scale_down_min_windows": cfg.get(
            "scale_down_min_windows",
            cfg.get("SCALE_DOWN_MIN_WINDOWS", 2),
        ),
        "scale_up_cooldown_seconds": cfg.get(
            "scale_up_cooldown_seconds",
            cfg.get("SCALE_UP_COOLDOWN_SECONDS", cfg.get("cooldown_seconds", 30)),
        ),
        "scale_down_cooldown_seconds": cfg.get(
            "scale_down_cooldown_seconds",
            cfg.get("SCALE_DOWN_COOLDOWN_SECONDS", 180),
        ),
        "average_cpu_utilization": cfg.get("average_cpu_utilization", cfg.get("cpu_target", 70)),
        # HAB Algorithm 2 parameters for Online Boutique.
        "hab_services": cfg.get("hab_services", cfg.get("services", ",".join([d for d in (app_cfg.get("deployments", []) or []) if d != "redis-cart"]))),
        "p_vector_json": cfg.get("p_vector_json", cfg.get("P_VECTOR_JSON", '{ "currencyservice": 1.00, "frontend": 0.63, "cartservice": 0.61, "recommendationservice": 0.55, "productcatalogservice": 0.54, "adservice": 0.13, "shippingservice": 0.09, "checkoutservice": 0.09, "emailservice": 0.04, "paymentservice": 0.03 }')),
        "lambda_base_rps": cfg.get("lambda_base_rps", cfg.get("LAMBDA_BASE_RPS", 139.11)),
        "phi_base": cfg.get("phi_base", cfg.get("PHI_BASE", 3.37)),
        "r_up_ms": cfg.get("r_up_ms", cfg.get("R_UP_MS", cfg.get("slo_ms", cfg.get("SLO_MS", 500)))),
        "r_low_ms": cfg.get("r_low_ms", cfg.get("R_LOW_MS", 400)),
        "hab_stabilization_seconds": cfg.get("hab_stabilization_seconds", cfg.get("HAB_STABILIZATION_SECONDS", 60)),
        "hab_post_proportional_wait_seconds": cfg.get("hab_post_proportional_wait_seconds", cfg.get("HAB_POST_PROPORTIONAL_WAIT_SECONDS", 60)),
        "hab_exploratory_enabled": str(cfg.get("hab_exploratory_enabled", cfg.get("HAB_EXPLORATORY_ENABLED", True))).lower(),
        "hab_exploratory_max_steps": cfg.get("hab_exploratory_max_steps", cfg.get("HAB_EXPLORATORY_MAX_STEPS", 3)),
        "hab_stable_lambda_rel_delta": cfg.get("hab_stable_lambda_rel_delta", cfg.get("HAB_STABLE_LAMBDA_REL_DELTA", 0.10)),
        "hab_scale_down_enabled": str(cfg.get("hab_scale_down_enabled", cfg.get("HAB_SCALE_DOWN_ENABLED", True))).lower(),
    })
    if deployment_name is not None:
        safe_name = _safe_k8s_name(deployment_name)
        controller_name = _controller_name_for(req.autoscaler_name, deployment_name)
        context.update({
            "deployment_name": deployment_name,
            "safe_deployment_name": safe_name,
            "target_deployment": deployment_name,
            "my_service": deployment_name,
            "controller_name": controller_name,
            "autoscaler_deployment_name": controller_name,
        })
        if req.autoscaler_name in CONTROLLER_DEPLOYMENT_AUTOSCALERS:
            context["autoscaler_name"] = controller_name

        # CustomDAS templates need peer-to-peer variables for every per-deployment
        # controller. The client may provide p2p_hub_deployment, but older clients
        # do not provide peer_id, p2p_hub_host, or is_p2p_hub. Fill safe defaults
        # here so setup and cleanup can render the same templates.
        if req.autoscaler_name in CUSTOMDAS_FAMILY_AUTOSCALERS:
            # Prefer the configured app root/latency deployment as the P2P hub.
            # This keeps Bookinfo on productpage-v1 and Online Boutique on frontend,
            # instead of accidentally choosing the first deployment in the app list.
            hub_deployment = cfg.get("p2p_hub_deployment", root_service or deployment_name)
            # The P2P hub Service must match the selected autoscaler variant.
            # For example:
            #   customdas          -> customdas-autoscaler-frontend
            #   customdas-cpu      -> customdas-cpu-autoscaler-frontend
            #   customdas-cpu-queue -> customdas-cpu-queue-autoscaler-frontend
            # Previously this was hard-coded to customdas-autoscaler-<hub>,
            # which broke DNS for customdas-cpu/customdas-cpu-queue workers.
            hub_controller_name = _controller_name_for(req.autoscaler_name, str(hub_deployment))
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
    if req.autoscaler_name == "dadqn":
        deployment_names = _validate_and_filter_dadqn_deployments(app_name, req.deployment_names, deployment_names)
    if req.autoscaler_name == "hab":
        deployment_names = _validate_and_filter_hab_deployments(app_name, req.deployment_names, deployment_names)
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
        if req.autoscaler_name in CONTROLLER_DEPLOYMENT_AUTOSCALERS:
            controller_names = [
                _controller_name_for(req.autoscaler_name, d)
                for d in deployment_names
            ]
            wait_for_deployments(namespace, controller_names)
        elif req.autoscaler_name in SHARED_DEPLOYMENT_AUTOSCALERS:
            wait_for_deployments(namespace, SHARED_DEPLOYMENT_AUTOSCALERS[req.autoscaler_name])

        for deployment_name in deployment_names:
            result: dict[str, Any] = {
                "deployment": deployment_name,
                "autoscaler": req.autoscaler_name,
                "action": "applied",
            }
#            if req.autoscaler_name == "das":
#                safe_name = _safe_k8s_name(deployment_name)
#                result["controller_name"] = f"das-autoscaler-{safe_name}"
            if req.autoscaler_name in CONTROLLER_DEPLOYMENT_AUTOSCALERS:
                result["controller_name"] = _controller_name_for(req.autoscaler_name, deployment_name)
            elif req.autoscaler_name in SHARED_DEPLOYMENT_AUTOSCALERS:
                result["controller_name"] = SHARED_DEPLOYMENT_AUTOSCALERS[req.autoscaler_name][0]
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
    #             safe_name = _safe_k8s_name(deployment_name)
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
    "Service": ("core", "namespaced", "service"),
    "ConfigMap": ("core", "namespaced", "config_map"),
    "Role": ("rbac", "namespaced", "role"),
    "RoleBinding": ("rbac", "namespaced", "role_binding"),
    "Deployment": ("apps", "namespaced", "deployment"),
    "HorizontalPodAutoscaler": ("autoscaling", "namespaced", "horizontal_pod_autoscaler"),
}



def _autoscaler_service_object(autoscaler_name: str, deployment_name: str, namespace: str) -> dict[str, Any]:
    safe_name = _safe_k8s_name(deployment_name)
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": f"{autoscaler_name}-autoscaler-{safe_name}",
            "namespace": namespace,
        },
    }


def _append_companion_service_objects(
    objects: list[dict[str, Any]],
    autoscaler_name: str,
    deployment_names: list[str],
    namespace: str,
) -> list[dict[str, Any]]:
    if autoscaler_name not in COMPANION_SERVICE_AUTOSCALERS:
        return objects

    # DAS/CustomDAS controllers use the same per-deployment naming convention
    # for companion Services as for controller Deployments. Some templates render
    # these Services explicitly, while older DAS manifests may not; add them here
    # so cleanup removes Services as well as Deployments in both cases.
    return [
        *objects,
        *(
            _autoscaler_service_object(autoscaler_name, deployment_name, namespace)
            for deployment_name in deployment_names
        ),
    ]


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
        if autoscaler_name == "dadqn":
            resolved_deployments = _validate_and_filter_dadqn_deployments(app_name, deployment_names, resolved_deployments)
        if autoscaler_name == "hab":
            resolved_deployments = _validate_and_filter_hab_deployments(app_name, deployment_names, resolved_deployments)
        req = DeployAutoscalerRequest(
            namespace=namespace,
            deployment_names=resolved_deployments,
            autoscaler_name=autoscaler_name,
            config={},
        )
        objects = _render_autoscaler_objects(req, resolved_deployments, app_name)
        objects = _append_companion_service_objects(objects, autoscaler_name, resolved_deployments, namespace)
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
