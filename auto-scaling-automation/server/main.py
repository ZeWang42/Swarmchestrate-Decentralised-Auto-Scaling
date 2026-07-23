
from __future__ import annotations

from fastapi import FastAPI
from kubernetes import config

from api.deploy_api import router as deploy_router
from api.experiment_api import router as experiment_router
from api.monitor_api import router as monitor_router
from config import MONITOR_LOG_DIR

app = FastAPI(title="Autoscaling Experiment Server", version="0.4.0")

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

app.include_router(deploy_router)
app.include_router(monitor_router)
app.include_router(experiment_router)
