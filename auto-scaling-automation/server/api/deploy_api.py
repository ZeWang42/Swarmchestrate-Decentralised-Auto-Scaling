from fastapi import APIRouter

from experiment.deploy_logic import (
    app_status_logic,
    bookinfo_status_logic,
    delete_app_autoscaler_logic,
    delete_app_logic,
    delete_bookinfo_autoscaler_logic,
    delete_bookinfo_logic,
    delete_onlineboutique_autoscaler_logic,
    delete_onlineboutique_logic,
    deploy_app_autoscaler_logic,
    deploy_app_logic,
    deploy_bookinfo_autoscaler_logic,
    deploy_bookinfo_logic,
    deploy_onlineboutique_autoscaler_logic,
    deploy_onlineboutique_logic,
    onlineboutique_status_logic,
)
from experiment.models import DeployAppRequest, DeployAppResponse, DeployAutoscalerRequest, DeployAutoscalerResponse, DeleteAutoscalerResponse

router = APIRouter()


@router.post("/deploy/{app_name}", response_model=DeployAppResponse)
def deploy_app(app_name: str, req: DeployAppRequest | None = None) -> DeployAppResponse:
    return deploy_app_logic(app_name, req)


@router.delete("/deploy/{app_name}")
def delete_app(app_name: str, namespace: str = "default"):
    return delete_app_logic(app_name, namespace)


@router.get("/deploy/{app_name}/status")
def app_status(app_name: str, namespace: str = "default"):
    return app_status_logic(app_name, namespace)


@router.post("/deploy/{app_name}/autoscaler", response_model=DeployAutoscalerResponse)
def deploy_app_autoscaler(app_name: str, req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    return deploy_app_autoscaler_logic(app_name, req)


@router.delete("/deploy/{app_name}/autoscaler", response_model=DeleteAutoscalerResponse)
def delete_app_autoscaler(app_name: str, namespace: str = "default", autoscaler_name: str = "default_cpu") -> DeleteAutoscalerResponse:
    return delete_app_autoscaler_logic(app_name, namespace, autoscaler_name)


# Explicit routes retained for clients that already call these endpoints.
@router.post("/deploy/bookinfo", response_model=DeployAppResponse)
def deploy_bookinfo(req: DeployAppRequest | None = None) -> DeployAppResponse:
    return deploy_bookinfo_logic(req)


@router.delete("/deploy/bookinfo")
def delete_bookinfo(namespace: str = "default"):
    return delete_bookinfo_logic(namespace)


@router.get("/deploy/bookinfo/status")
def bookinfo_status(namespace: str = "default"):
    return bookinfo_status_logic(namespace)


@router.post("/deploy/bookinfo/autoscaler", response_model=DeployAutoscalerResponse)
def deploy_bookinfo_autoscaler(req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    return deploy_bookinfo_autoscaler_logic(req)


@router.delete("/deploy/bookinfo/autoscaler", response_model=DeleteAutoscalerResponse)
def delete_bookinfo_autoscaler(namespace: str = "default", autoscaler_name: str = "default_cpu") -> DeleteAutoscalerResponse:
    return delete_bookinfo_autoscaler_logic(namespace, autoscaler_name)


@router.post("/deploy/onlineboutique", response_model=DeployAppResponse)
def deploy_onlineboutique(req: DeployAppRequest | None = None) -> DeployAppResponse:
    return deploy_onlineboutique_logic(req)


@router.delete("/deploy/onlineboutique")
def delete_onlineboutique(namespace: str = "default"):
    return delete_onlineboutique_logic(namespace)


@router.get("/deploy/onlineboutique/status")
def onlineboutique_status(namespace: str = "default"):
    return onlineboutique_status_logic(namespace)


@router.post("/deploy/onlineboutique/autoscaler", response_model=DeployAutoscalerResponse)
def deploy_onlineboutique_autoscaler(req: DeployAutoscalerRequest | None = None) -> DeployAutoscalerResponse:
    return deploy_onlineboutique_autoscaler_logic(req)


@router.delete("/deploy/onlineboutique/autoscaler", response_model=DeleteAutoscalerResponse)
def delete_onlineboutique_autoscaler(namespace: str = "default", autoscaler_name: str = "default_cpu") -> DeleteAutoscalerResponse:
    return delete_onlineboutique_autoscaler_logic(namespace, autoscaler_name)
