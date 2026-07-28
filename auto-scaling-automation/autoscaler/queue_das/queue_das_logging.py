from __future__ import annotations
from typing import Any

def build_deployment_monitoring_log(
    deployment: str,
    cpu_m: float | int | None,
    mem_mib: float | int | None,
    pods_count: int,
    cpu_utilisation: float,
    mem_utilisation: float,

    http_rpm_as_dst: float,
    grpc_rpm_as_dst: float,
    http_latency_p50_as_dst: float,
    grpc_latency_p50_as_dst: float,
    http_latency_p90_as_dst: float,
    grpc_latency_p90_as_dst: float,
    http_latency_p95_as_dst: float,
    grpc_latency_p95_as_dst: float,

    http_rpm_as_src: float,
    grpc_rpm_as_src: float,
    http_latency_p50_as_src: float,
    grpc_latency_p50_as_src: float,
    http_latency_p90_as_src: float,
    grpc_latency_p90_as_src: float,
    http_latency_p95_as_src: float,
    grpc_latency_p95_as_src: float,

    http_rpm_mesh_as_dst: dict[str, float] | None,
    grpc_rpm_mesh_as_dst: dict[str, float] | None,
    http_latency_mesh_avg_as_dst: dict[str, float] | None,
    grpc_latency_mesh_avg_as_dst: dict[str, float] | None,
    http_latency_p95_mesh_as_dst: dict[str, float] | None,
    grpc_latency_p95_mesh_as_dst: dict[str, float] | None,
    http_latency_p90_mesh_as_dst: dict[str, float] | None = None,
    grpc_latency_p90_mesh_as_dst: dict[str, float] | None = None,

    http_rpm_mesh_as_src: dict[str, float] | None = None,
    grpc_rpm_mesh_as_src: dict[str, float] | None = None,
    http_latency_mesh_avg_as_src: dict[str, float] | None = None,
    grpc_latency_mesh_avg_as_src: dict[str, float] | None = None,
    http_latency_p95_mesh_as_src: dict[str, float] | None = None,
    grpc_latency_p95_mesh_as_src: dict[str, float] | None = None,
    http_latency_p90_mesh_as_src: dict[str, float] | None = None,
    grpc_latency_p90_mesh_as_src: dict[str, float] | None = None,

    upstreams: list[str] | None = None,
    downstreams: list[str] | None = None,
    selected_tail_label: str = "P95",
) -> str:
    """
    Builds a highly scannable, structured telemetry block containing resources, 
    aggregated inbound/outbound transit traffic metrics, and distributed microservice mesh maps.
    """
    # Safe value formatting helpers
    def fmt_num(val: Any, suffix: str = "", digits: int = 2) -> str:
        if val is None:
            return "N/A"
        if isinstance(val, (int, float)):
            return f"{val:.{digits}f}{suffix}" if isinstance(val, float) else f"{val}{suffix}"
        return str(val)

    tail_label = (selected_tail_label or "P95").upper()

    def fmt_dict_mesh(rpm_dict: dict[str, float] | None, avg_dict: dict[str, float] | None, tail_dict: dict[str, float] | None) -> str:
        if not rpm_dict and not avg_dict and not tail_dict:
            return "    No dynamic mesh traffic tracked.\n"
        
        # Combine all known keys across dictionaries
        keys = set(rpm_dict.keys() if rpm_dict else [])
        keys.update(avg_dict.keys() if avg_dict else [])
        keys.update(tail_dict.keys() if tail_dict else [])
        
        lines = []
        for k in sorted(keys):
            rpm = rpm_dict.get(k, 0.0) if rpm_dict else 0.0
            avg = avg_dict.get(k, 0.0) if avg_dict else 0.0
            tail = tail_dict.get(k, 0.0) if tail_dict else 0.0
            lines.append(f"    -> {k:<22} | Intensity: {rpm:>7.1f} RPM | Avg: {avg:>6.1f} ms | {tail_label}: {tail:>6.1f} ms")
        return "\n".join(lines) + "\n"

    # Select the mesh tail dictionaries displayed in the breakdown tables.
    selected_http_mesh_tail_dst = http_latency_p90_mesh_as_dst if tail_label == "P90" else http_latency_p95_mesh_as_dst
    selected_grpc_mesh_tail_dst = grpc_latency_p90_mesh_as_dst if tail_label == "P90" else grpc_latency_p95_mesh_as_dst
    selected_http_mesh_tail_src = http_latency_p90_mesh_as_src if tail_label == "P90" else http_latency_p95_mesh_as_src
    selected_grpc_mesh_tail_src = grpc_latency_p90_mesh_as_src if tail_label == "P90" else grpc_latency_p95_mesh_as_src

    # Assemble Topology Maps
    upstream_str = ", ".join(upstreams) if upstreams else "None"
    downstream_str = ", ".join(downstreams) if downstreams else "None"

    log_output = (
        "\n"
        "=== Deployment Monitoring Log ===\n"
        f"Deployment Focus Target: {deployment}\n"
        f"Topology Relationships : [Upstreams: {upstream_str}] -> [Downstreams: {downstream_str}]\n"
        "\n"
        "[Resources Data]\n"
        f"  Allocated CPU (m)       : {fmt_num(cpu_m)}\n"
        f"  Allocated Memory (MiB)  : {fmt_num(mem_mib)}\n"
        f"  Active Running Pods (c) : {pods_count}\n"
        f"  Realtime CPU Util (%)   : {fmt_num(cpu_utilisation, '%')}\n"
        f"  Realtime Memory Util (%): {fmt_num(mem_utilisation, '%')}\n"
        "\n"
        "[Aggregate Traffic as Destination (Inbound Requests)]\n"
        f"  HTTP Volume Load        : {fmt_num(http_rpm_as_dst, ' RPM')}\n"
        f"  gRPC Volume Load        : {fmt_num(grpc_rpm_as_dst, ' RPM')}\n"
        f"  Transit Latencies (ms)  : P50: {fmt_num(http_latency_p50_as_dst + grpc_latency_p50_as_dst):>6} | "
        f"P90: {fmt_num(http_latency_p90_as_dst + grpc_latency_p90_as_dst):>6} | "
        f"P95: {fmt_num(http_latency_p95_as_dst + grpc_latency_p95_as_dst):>6}\n"
        "\n"
        "[Aggregate Traffic as Source (Outbound Dependency Calls)]\n"
        f"  HTTP Despatched Volume  : {fmt_num(http_rpm_as_src, ' RPM')}\n"
        f"  gRPC Despatched Volume  : {fmt_num(grpc_rpm_as_src, ' RPM')}\n"
        f"  Transit Latencies (ms)  : P50: {fmt_num(http_latency_p50_as_src + grpc_latency_p50_as_src):>6} | "
        f"P90: {fmt_num(http_latency_p90_as_src + grpc_latency_p90_as_src):>6} | "
        f"P95: {fmt_num(http_latency_p95_as_src + grpc_latency_p95_as_src):>6}\n"
        "\n"
        "[Mesh Traffic as Destination (Breakdown Per Inbound Upstream Workload)]\n"
        f"{fmt_dict_mesh(http_rpm_mesh_as_dst, http_latency_mesh_avg_as_dst, selected_http_mesh_tail_dst)}"
        f"{fmt_dict_mesh(grpc_rpm_mesh_as_dst, grpc_latency_mesh_avg_as_dst, selected_grpc_mesh_tail_dst)}"
        "\n"
        "[Mesh Traffic as Source (Breakdown Per Outbound Downstream Workload)]\n"
        f"{fmt_dict_mesh(http_rpm_mesh_as_src, http_latency_mesh_avg_as_src, selected_http_mesh_tail_src)}"
        f"{fmt_dict_mesh(grpc_rpm_mesh_as_src, grpc_latency_mesh_avg_as_src, selected_grpc_mesh_tail_src)}"
        "===============================================================\n"
    )

    return log_output
