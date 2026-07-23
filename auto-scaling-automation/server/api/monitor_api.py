
from fastapi import APIRouter

from experiment.models import StartMonitorRequest, MonitorStatusResponse
from experiment.monitor_logic import start_monitor_logic, stop_monitor_logic, monitor_status_logic

router = APIRouter()

@router.post("/monitor/start", response_model=MonitorStatusResponse)
def start_monitor(req: StartMonitorRequest | None = None) -> MonitorStatusResponse:
    return start_monitor_logic(req)

@router.post("/monitor/stop", response_model=MonitorStatusResponse)
def stop_monitor() -> MonitorStatusResponse:
    return stop_monitor_logic()

@router.get("/monitor/status", response_model=MonitorStatusResponse)
def monitor_status() -> MonitorStatusResponse:
    return monitor_status_logic()
