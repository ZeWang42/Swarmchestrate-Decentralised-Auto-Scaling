from __future__ import annotations

from typing import Any


ROOT_SERVICES = {"frontend"}
EXTERNAL_UPSTREAMS = {"gateway", "istio-ingressgateway", "unknown", ""}


def is_nonzero(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, dict):
        return any(is_nonzero(v) for v in value.values())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return bool(value)


def fmt(value: Any, digits: int = 2) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def merge_metric(http_value: float | None, grpc_value: float | None) -> float:
    return (http_value or 0.0) + (grpc_value or 0.0)


def merge_dict_metric(
    http_dict: dict[str, float] | None,
    grpc_dict: dict[str, float] | None,
) -> dict[str, float]:
    merged: dict[str, float] = {}

    for d in (http_dict or {}, grpc_dict or {}):
        for key, value in d.items():
            if key in EXTERNAL_UPSTREAMS:
                continue
            merged[key] = merged.get(key, 0.0) + (value or 0.0)

    return {k: v for k, v in merged.items() if is_nonzero(v)}


def classify_node(
    deployment: str,
    upstreams: list[str],
    downstreams: list[str],
) -> str:
    if deployment in ROOT_SERVICES:
        return "root"
    if downstreams:
        return "intermediate"
    return "leaf"


def top_p95_bottlenecks(
    deployment: str,
    node_type: str,
    downstream_p95: dict[str, float],
) -> list[tuple[str, float | str]]:
    if node_type == "leaf":
        return [(deployment, "self")]

    ranked = sorted(
        downstream_p95.items(),
        key=lambda item: item[1] or 0.0,
        reverse=True,
    )

    return ranked[:3]


def log_if(lines: list[str], label: str, value: Any, suffix: str = "") -> None:
    if is_nonzero(value):
        lines.append(f"{label}: {fmt(value)}{suffix}")


def build_deployment_monitoring_log(
    *,
    deployment: str,
    cpu_m: float,
    mem_mib: float,
    pods_count: int,
    cpu_utilisation: float,
    mem_utilisation: float,

    http_rpm_as_dst: float,
    grpc_rpm_as_dst: float,
    http_latency_p50_as_dst: float,
    grpc_latency_p50_as_dst: float,
    http_latency_avg_as_dst: float,
    grpc_latency_avg_as_dst: float,
    http_latency_p95_as_dst: float,
    grpc_latency_p95_as_dst: float,

    http_rpm_as_src: float,
    grpc_rpm_as_src: float,
    http_latency_p50_as_src: float,
    grpc_latency_p50_as_src: float,
    http_latency_avg_as_src: float,
    grpc_latency_avg_as_src: float,
    http_latency_p95_as_src: float,
    grpc_latency_p95_as_src: float,

    http_rpm_mesh_as_dst: dict[str, float],
    grpc_rpm_mesh_as_dst: dict[str, float],
    http_latency_mesh_avg_as_dst: dict[str, float],
    grpc_latency_mesh_avg_as_dst: dict[str, float],
    http_latency_p95_mesh_as_dst: dict[str, float],
    grpc_latency_p95_mesh_as_dst: dict[str, float],

    http_rpm_mesh_as_src: dict[str, float],
    grpc_rpm_mesh_as_src: dict[str, float],
    http_latency_mesh_avg_as_src: dict[str, float],
    grpc_latency_mesh_avg_as_src: dict[str, float],
    http_latency_p95_mesh_as_src: dict[str, float],
    grpc_latency_p95_mesh_as_src: dict[str, float],

    upstreams: list[str],
    downstreams: list[str],
) -> str:
    upstreams = sorted(
        u for u in upstreams
        if u not in EXTERNAL_UPSTREAMS
    )
    downstreams = sorted(
        d for d in downstreams
        if d not in EXTERNAL_UPSTREAMS
    )

    node_type = classify_node(deployment, upstreams, downstreams)

    rpm_as_dst = merge_metric(http_rpm_as_dst, grpc_rpm_as_dst)
    rpm_as_src = merge_metric(http_rpm_as_src, grpc_rpm_as_src)

    dst_p50 = merge_metric(http_latency_p50_as_dst, grpc_latency_p50_as_dst)
    dst_avg = merge_metric(http_latency_avg_as_dst, grpc_latency_avg_as_dst)
    dst_p95 = merge_metric(http_latency_p95_as_dst, grpc_latency_p95_as_dst)

    src_p50 = merge_metric(http_latency_p50_as_src, grpc_latency_p50_as_src)
    src_avg = merge_metric(http_latency_avg_as_src, grpc_latency_avg_as_src)
    src_p95 = merge_metric(http_latency_p95_as_src, grpc_latency_p95_as_src)

    rpm_mesh_dst = merge_dict_metric(http_rpm_mesh_as_dst, grpc_rpm_mesh_as_dst)
    rpm_mesh_src = merge_dict_metric(http_rpm_mesh_as_src, grpc_rpm_mesh_as_src)

    avg_mesh_dst = merge_dict_metric(
        http_latency_mesh_avg_as_dst,
        grpc_latency_mesh_avg_as_dst,
    )
    p95_mesh_dst = merge_dict_metric(
        http_latency_p95_mesh_as_dst,
        grpc_latency_p95_mesh_as_dst,
    )

    avg_mesh_src = merge_dict_metric(
        http_latency_mesh_avg_as_src,
        grpc_latency_mesh_avg_as_src,
    )
    p95_mesh_src = merge_dict_metric(
        http_latency_p95_mesh_as_src,
        grpc_latency_p95_mesh_as_src,
    )

    bottlenecks = top_p95_bottlenecks(
        deployment=deployment,
        node_type=node_type,
        downstream_p95=p95_mesh_src,
    )

    lines: list[str] = []

    lines.append("\n=== Deployment Monitoring ===")
    lines.append(f"Deployment: {deployment}")

    lines.append("\n[Node]")
    lines.append(f"Type: {node_type}")
    lines.append(f"Upstreams: {upstreams if upstreams else 'None'}")
    lines.append(f"Downstreams: {downstreams if downstreams else 'None'}")

    lines.append("\n[Resources]")
    log_if(lines, "CPU (m)", cpu_m)
    log_if(lines, "Memory (MiB)", mem_mib)
    log_if(lines, "Running Pods", pods_count)
    log_if(lines, "CPU Utilisation (%)", cpu_utilisation)
    log_if(lines, "Memory Utilisation (%)", mem_utilisation)

    lines.append("\n[Aggregate Traffic as Destination]")
    log_if(lines, "RPM as dst", rpm_as_dst)
    log_if(lines, "dst_p50 (ms)", dst_p50)
    log_if(lines, "dst_avg (ms)", dst_avg)
    log_if(lines, "dst_p95 (ms)", dst_p95)

    lines.append("\n[Aggregate Traffic as Source]")
    log_if(lines, "RPM as src", rpm_as_src)
    log_if(lines, "src_p50 (ms)", src_p50)
    log_if(lines, "src_avg (ms)", src_avg)
    log_if(lines, "src_p95 (ms)", src_p95)

    if is_nonzero(rpm_mesh_dst) or is_nonzero(avg_mesh_dst) or is_nonzero(p95_mesh_dst):
        lines.append("\n[Mesh Traffic as Destination: per upstream]")
        log_if(lines, "RPM from upstreams", rpm_mesh_dst)
        log_if(lines, "Latency Avg from upstreams (ms)", avg_mesh_dst)
        log_if(lines, "Latency P95 from upstreams (ms)", p95_mesh_dst)

    if is_nonzero(rpm_mesh_src) or is_nonzero(avg_mesh_src) or is_nonzero(p95_mesh_src):
        lines.append("\n[Mesh Traffic as Source: per downstream]")
        log_if(lines, "RPM to downstreams", rpm_mesh_src)
        log_if(lines, "Latency Avg to downstreams (ms)", avg_mesh_src)
        log_if(lines, "Latency P95 to downstreams (ms)", p95_mesh_src)

    lines.append("\n[Potential Bottlenecks]")
    if node_type == "leaf":
        lines.append(f"1. {deployment}: self")
    elif bottlenecks:
        for i, (service, p95) in enumerate(bottlenecks, start=1):
            lines.append(f"{i}. {service}: p95={float(p95):.2f} ms")
    else:
        lines.append("None detected")

    return "\n".join(lines)