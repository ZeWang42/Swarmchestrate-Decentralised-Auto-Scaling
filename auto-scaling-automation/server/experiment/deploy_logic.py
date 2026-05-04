from __future__ import annotations
from fastapi import HTTPException

from config import APPLICATIONS, BOOKINFO_APP_NAME, DEFAULT_NAMESPACE, ONLINEBOUTIQUE_APP_NAME
from experiment.models import DeployAppRequest, DeployAppResponse, DeployAutoscalerRequest, DeployAutoscalerResponse, DeleteAutoscalerResponse
from k8s.app_ops import deploy_application, delete_application, application_status
from k8s.hpa_ops import deploy_autoscaler_for_application, delete_autoscaler_for_application


def _get_app_config(app_name: str) -> dict:
    app_key = app_name.strip().lower()
    cfg = APPLICATIONS.get(app_key)
    if cfg is None:
        raise HTTPException(status_code=400, detail=f"Unsupported app: {app_name}. Supported apps: {sorted(APPLICATIONS)}")
    return cfg


def deploy_app_logic(app_name: str, req: DeployAppRequest | None = None) -> DeployAppResponse:
    cfg = _get_app_config(app_name)
    request = req or DeployAppRequest(
        namespace=DEFAULT_NAMESPACE,
        manifest_path=cfg["manifest"],
        gateway_manifest_path=cfg["gateway_manifest"],
        create_namespace=False,
    )
    return deploy_application(cfg["name"], request)


def delete_app_logic(app_name: str, namespace: str = DEFAULT_NAMESPACE):
    cfg = _get_app_config(app_name)
    return delete_application(cfg["name"], namespace, [cfg["gateway_manifest"], cfg["manifest"]])


def app_status_logic(app_name: str, namespace: str = DEFAULT_NAMESPACE):
    cfg = _get_app_config(app_name)
    return application_status(cfg["name"], namespace, cfg["deployments"], cfg["services"])


def deploy_app_autoscaler_logic(app_name: str, req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    cfg = _get_app_config(app_name)
    request = req or DeployAutoscalerRequest(namespace=DEFAULT_NAMESPACE, autoscaler_name="default_cpu", config={"min_replicas": 1, "max_replicas": 5, "average_cpu_utilization": 70})
    return deploy_autoscaler_for_application(cfg["name"], request)


def delete_app_autoscaler_logic(app_name: str, namespace: str = DEFAULT_NAMESPACE, autoscaler_name: str = "default_cpu", deployment_names: list[str] | None = None) -> DeleteAutoscalerResponse:
    cfg = _get_app_config(app_name)
    return delete_autoscaler_for_application(cfg["name"], namespace, autoscaler_name, deployment_names)


# Backward-compatible Bookinfo helpers used by older clients/tests.
def deploy_bookinfo_logic(req: DeployAppRequest | None = None) -> DeployAppResponse:
    return deploy_app_logic(BOOKINFO_APP_NAME, req)


def delete_bookinfo_logic(namespace: str = DEFAULT_NAMESPACE):
    return delete_app_logic(BOOKINFO_APP_NAME, namespace)


def bookinfo_status_logic(namespace: str = DEFAULT_NAMESPACE):
    return app_status_logic(BOOKINFO_APP_NAME, namespace)


def deploy_bookinfo_autoscaler_logic(req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    return deploy_app_autoscaler_logic(BOOKINFO_APP_NAME, req)


def delete_bookinfo_autoscaler_logic(namespace: str = DEFAULT_NAMESPACE, autoscaler_name: str = "default_cpu") -> DeleteAutoscalerResponse:
    return delete_app_autoscaler_logic(BOOKINFO_APP_NAME, namespace, autoscaler_name)


# Online Boutique helpers mirroring Bookinfo.
def deploy_onlineboutique_logic(req: DeployAppRequest | None = None) -> DeployAppResponse:
    return deploy_app_logic(ONLINEBOUTIQUE_APP_NAME, req)


def delete_onlineboutique_logic(namespace: str = DEFAULT_NAMESPACE):
    return delete_app_logic(ONLINEBOUTIQUE_APP_NAME, namespace)


def onlineboutique_status_logic(namespace: str = DEFAULT_NAMESPACE):
    return app_status_logic(ONLINEBOUTIQUE_APP_NAME, namespace)


def deploy_onlineboutique_autoscaler_logic(req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    return deploy_app_autoscaler_logic(ONLINEBOUTIQUE_APP_NAME, req)


def delete_onlineboutique_autoscaler_logic(namespace: str = DEFAULT_NAMESPACE, autoscaler_name: str = "default_cpu") -> DeleteAutoscalerResponse:
    return delete_app_autoscaler_logic(ONLINEBOUTIQUE_APP_NAME, namespace, autoscaler_name)
