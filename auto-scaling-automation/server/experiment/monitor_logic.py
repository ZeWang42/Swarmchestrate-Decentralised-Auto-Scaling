
from __future__ import annotations

import time
import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from config import DEFAULT_NAMESPACE, MONITOR_LOG_DIR, latency_deployments
from experiment.models import StartMonitorRequest, MonitorStatusResponse
from k8s.metrics_ops import (
    get_autoscaler_deployments,
    get_deployments,
    get_nodes,
    node_usage,
    node_utilization_percent,
    query_prometheus,
    service_pod_metrics,
)
from utils.parsing import round1
from utils.formatting import safe_prefix

_monitor_thread: threading.Thread | None = None
_monitor_stop_event = threading.Event()
_monitor_state: dict[str, Any] = {
    "running": False,
    "namespace": None,
    "interval": None,
    "prom_url": None,
    "autoscaler_name": None,
    "latency_percentile": None,
    "log_file": None,
    "started_at": None,
}

def start_monitor_logic(req: StartMonitorRequest | None = None) -> MonitorStatusResponse:
    global _monitor_thread

    request = req or StartMonitorRequest(namespace=DEFAULT_NAMESPACE)
    if _monitor_state["running"]:
        raise HTTPException(status_code=409, detail="Monitor is already running")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = MONITOR_LOG_DIR / f"{safe_prefix(request.file_prefix)}_{request.namespace}_{request.interval}s_{timestamp}.csv"

    _monitor_stop_event.clear()
    _monitor_state.update({
        "running": True,
        "namespace": request.namespace,
        "interval": request.interval,
        "prom_url": request.prom_url,
        "autoscaler_name": request.autoscaler_name,
        "latency_percentile": request.latency_percentile,
        "log_file": str(log_file),
        "started_at": datetime.now().isoformat(),
    })

    _monitor_thread = threading.Thread(
        target=_monitor_loop,
        kwargs={
            "namespace": request.namespace,
            "interval": request.interval,
            "prom_url": request.prom_url,
            "autoscaler_name": request.autoscaler_name,
            "latency_percentile": request.latency_percentile,
            "log_file": log_file,
        },
        daemon=True,
    )
    _monitor_thread.start()
    return MonitorStatusResponse(ok=True, **_monitor_state)


def stop_monitor_logic() -> MonitorStatusResponse:
    if not _monitor_state["running"]:
        raise HTTPException(status_code=409, detail="Monitor is not running")
    _monitor_stop_event.set()
    return MonitorStatusResponse(
        ok=True,
        running=False,
        namespace=_monitor_state["namespace"],
        interval=_monitor_state["interval"],
        prom_url=_monitor_state["prom_url"],
        autoscaler_name=_monitor_state["autoscaler_name"],
        latency_percentile=_monitor_state["latency_percentile"],
        log_file=_monitor_state["log_file"],
        started_at=_monitor_state["started_at"],
    )

def monitor_status_logic() -> MonitorStatusResponse:
    return MonitorStatusResponse(ok=True, **_monitor_state)

#def _monitor_loop(namespace: str, interval: int, prom_url: str, autoscaler_name: str | None, log_file: Path) -> None:
#    try:
#        with log_file.open("w", newline="", encoding="utf-8") as f:
#            writer = csv.writer(f)
#            writer.writerow([
#                "Timestamp", "Scope", "Name", "HTTP_RPM", "HTTP_LAT_ms", "gRPC_RPM", "gRPC_LAT_ms",
#                "CPU_m", "MEM_MiB", "Pods", "CPU_pct", "MEM_pct", "NET_RX_Bps", "NET_TX_Bps",
#            ])
#
#            while not _monitor_stop_event.is_set():
#                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#
#                try:
#                    for svc in get_deployments(namespace):
#                        http_rpm = query_prometheus(prom_url, f'sum(rate(istio_requests_total{{request_protocol="http", destination_workload="{svc}"}}[30s])) * 60')
#                        http_lat = query_prometheus(prom_url, f'sum(rate(istio_request_duration_milliseconds_sum{{request_protocol="http", destination_workload="{svc}"}}[30s])) / sum(rate(istio_request_duration_milliseconds_count{{request_protocol="http", destination_workload="{svc}"}}[30s]))')
#                        grpc_rpm = query_prometheus(prom_url, f'sum(rate(istio_requests_total{{request_protocol="grpc", destination_workload="{svc}"}}[30s])) * 60')
#                        grpc_lat = query_prometheus(prom_url, f'sum(rate(istio_request_duration_milliseconds_sum{{request_protocol="grpc", destination_workload="{svc}"}}[30s])) / sum(rate(istio_request_duration_milliseconds_count{{request_protocol="grpc", destination_workload="{svc}"}}[30s]))')
#
#                        cpu_m, mem_mib, pods = service_pod_metrics(namespace, svc)
#
#                        writer.writerow([
#                            ts, "service", svc,
#                            round1(http_rpm), round1(http_lat),
#                            round1(grpc_rpm), round1(grpc_lat),
#                            cpu_m, mem_mib, pods,
#                            "", "", "", ""
#                        ])
#                    f.flush()
#
#                except Exception as exc:
#                    writer.writerow([
#                        ts, "service_error", namespace, str(exc),
#                        "", "", "", "", "", "", "", "", "", ""
#                    ])
#                    f.flush()
#
#                try:
#                    for node in get_nodes():
#                        cpu_m, mem_mib = node_usage(node)
#                        cpu_pct, mem_pct = node_utilization_percent(node)
#
#                        net_rx_bps = query_prometheus(prom_url, f'sum(rate(node_network_receive_bytes_total{{instance=~".*{node}.*",device!~"lo|veth.*|cali.*|flannel.*|cni.*"}}[30s]))')
#                        net_tx_bps = query_prometheus(prom_url, f'sum(rate(node_network_transmit_bytes_total{{instance=~".*{node}.*",device!~"lo|veth.*|cali.*|flannel.*|cni.*"}}[30s]))')
#
#                        writer.writerow([
#                            ts, "node", node,
#                            "", "", "", "",
#                            cpu_m, mem_mib, "",
#                            round1(cpu_pct), round1(mem_pct),
#                            round1(net_rx_bps), round1(net_tx_bps)
#                        ])
#                    f.flush()
#
#                except Exception as exc:
#                    writer.writerow([
#                        ts, "node_error", "cluster", str(exc),
#                        "", "", "", "", "", "", "", "", "", ""
#                    ])
#                    f.flush()
#
#                _monitor_stop_event.wait(interval)
#
#    finally:
#        _monitor_state["running"] = False

def _monitor_loop(
    namespace: str,
    interval: int,
    prom_url: str,
    autoscaler_name: str | None,
    latency_percentile: str,
    log_file: Path,
) -> None:
    try:
        with log_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Timestamp",
                "Scope",
                "Name",
                "CPU_m",
                "MEM_MiB",
                "Pods",
                "CPU_pct",
                "MEM_pct",
                "HTTP_LAT_ms",
            ])

            while not _monitor_stop_event.is_set():
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                try:
                    for deployment in get_deployments(namespace):
                        cpu_m, mem_mib, pods = service_pod_metrics(namespace, deployment)

                        writer.writerow([
                            ts,
                            "deployment",
                            deployment,
                            cpu_m,
                            mem_mib,
                            pods,
                            "",
                            "",
                            "",
                        ])

                        if deployment in latency_deployments():
                            quantile = {
                                "p90": 0.90,
                                "p95": 0.95,
                            }[latency_percentile]
                            http_latency = query_prometheus(
                                prom_url,
                                f'histogram_quantile({quantile}, '
                                f'sum(rate(istio_request_duration_milliseconds_bucket{{request_protocol="http", destination_workload="{deployment}"}}[1m])) '
                                f'by (le))'
                            )

                            writer.writerow([
                                ts,
                                f"http_{latency_percentile}_latency",
                                deployment,
                                "",
                                "",
                                "",
                                "",
                                "",
                                round1(http_latency),
                            ])

                    f.flush()

                except Exception as exc:
                    writer.writerow([
                        ts,
                        "deployment_error",
                        namespace,
                        str(exc),
                        "",
                        "",
                        "",
                        "",
                        "",
                    ])
                    f.flush()

                try:
                    # Autoscaler controllers are monitored separately from the
                    # application so their operational overhead can be analysed.
                    for controller in get_autoscaler_deployments(namespace, autoscaler_name):
                        cpu_m, mem_mib, pods = service_pod_metrics(namespace, controller)
                        writer.writerow([
                            ts,
                            "autoscaler",
                            controller,
                            cpu_m,
                            mem_mib,
                            pods,
                            "",
                            "",
                            "",
                        ])
                    f.flush()
                except Exception as exc:
                    writer.writerow([
                        ts,
                        "autoscaler_error",
                        autoscaler_name or "none",
                        str(exc),
                        "",
                        "",
                        "",
                        "",
                        "",
                    ])
                    f.flush()

                try:
                    for node in get_nodes():
                        cpu_m, mem_mib = node_usage(node)
                        cpu_pct, mem_pct = node_utilization_percent(node)

                        writer.writerow([
                            ts,
                            "node",
                            node,
                            cpu_m,
                            mem_mib,
                            "",
                            round1(cpu_pct),
                            round1(mem_pct),
                            "",
                        ])

                    f.flush()

                except Exception as exc:
                    writer.writerow([
                        ts,
                        "node_error",
                        "cluster",
                        str(exc),
                        "",
                        "",
                        "",
                        "",
                        "",
                    ])
                    f.flush()

                _monitor_stop_event.wait(interval)

    finally:
        _monitor_state["running"] = False
