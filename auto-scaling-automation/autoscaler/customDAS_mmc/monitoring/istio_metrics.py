from __future__ import annotations

import requests


def check_prometheus(prom_url: str) -> bool:
    try:
        resp = requests.get(prom_url, params={"query": "up"}, timeout=5)
        resp.raise_for_status()
        return True
    except Exception:
        return False


def query_prometheus_scalar(prom_url: str, query: str) -> float:
    try:
        resp = requests.get(prom_url, params={"query": query}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        result = payload.get("data", {}).get("result", [])
        if not result:
            return 0.0
        return float(result[0].get("value", [None, "0"])[1])
    except Exception:
        return 0.0


def query_prometheus_vector(prom_url: str, query: str) -> list[dict]:
    try:
        resp = requests.get(prom_url, params={"query": query}, timeout=10)
        resp.raise_for_status()
        payload = resp.json()
        return payload.get("data", {}).get("result", [])
    except Exception:
        return []


# ----------------------------------------------------------------------
# Aggregate metrics for one destination workload
# ----------------------------------------------------------------------

def get_http_rpm_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_rpm_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p25_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p25_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p50_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return HTTP P50 latency as destination in milliseconds."""
    query = (
        'histogram_quantile(0.50, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p50_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return gRPC P50 latency as destination in milliseconds."""
    query = (
        'histogram_quantile(0.50, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p90_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return HTTP P90 latency as destination in milliseconds."""
    query = (
        'histogram_quantile(0.90, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p90_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return gRPC P90 latency as destination in milliseconds."""
    query = (
        'histogram_quantile(0.90, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p95_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p95_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}]))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}]))'
    )
    return query_prometheus_scalar(prom_url, query)


# ----------------------------------------------------------------------
# Aggregate metrics for one source workload
# ----------------------------------------------------------------------

def get_http_rpm_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_rpm_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p25_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return HTTP P25 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.25, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p25_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return gRPC P25 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.25, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p50_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return HTTP P50 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.50, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p50_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return gRPC P50 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.50, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p90_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return HTTP P90 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.90, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p90_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    """Return gRPC P90 latency as source in milliseconds."""
    query = (
        'histogram_quantile(0.90, '
        'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p95_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p95_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}])) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="http", source_workload="{deployment_name}"}}'
        f'[{period}]))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}])) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="grpc", source_workload="{deployment_name}"}}'
        f'[{period}]))'
    )
    return query_prometheus_scalar(prom_url, query)


# ----------------------------------------------------------------------
# Source -> destination mesh edge metrics
# ----------------------------------------------------------------------

def get_http_rpm_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_rpm_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p25_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p25_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p95_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p95_between(
    prom_url: str,
    source_workload: str,
    destination_workload: str,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", '
        f'source_workload="{source_workload}", '
        f'destination_workload="{destination_workload}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


# ----------------------------------------------------------------------
# Full mesh view for one destination workload
# Returns dict[source_workload] = value
# ----------------------------------------------------------------------

def get_http_rpm_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload) * 60'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_grpc_rpm_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload) * 60'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_http_latency_p25_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_grpc_latency_p25_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_http_latency_p90_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.90, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh



def get_http_latency_p95_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_grpc_latency_p90_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.90, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh



def get_grpc_latency_p95_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_http_latency_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="http", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload)'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


def get_grpc_latency_mesh_as_dst(
    prom_url: str,
    destination_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="grpc", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (source_workload)'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        source = item.get("metric", {}).get("source_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[source] = value

    return mesh


# ----------------------------------------------------------------------
# Full mesh view for one source workload
# Returns dict[destination_workload] = value
# ----------------------------------------------------------------------

def get_http_rpm_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload) * 60'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_grpc_rpm_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload) * 60'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_http_latency_p25_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_grpc_latency_p25_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.25, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_http_latency_p90_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.90, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh



def get_http_latency_p95_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_grpc_latency_p90_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.90, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh

def get_grpc_latency_p95_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload, le))'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_http_latency_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="http", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload)'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh


def get_grpc_latency_mesh_as_src(
    prom_url: str,
    source_workload: str,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'sum(rate(istio_request_duration_milliseconds_sum'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload) '
        f'/ '
        f'sum(rate(istio_request_duration_milliseconds_count'
        f'{{request_protocol="grpc", source_workload="{source_workload}"}}'
        f'[{period}])) by (destination_workload)'
    )

    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}

    for item in results:
        destination = item.get("metric", {}).get("destination_workload", "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[destination] = value

    return mesh

# ----------------------------------------------------------------------
# P10 latency helpers added for low-percentile monitoring
# ----------------------------------------------------------------------

def _latency_quantile_scalar(
    prom_url: str,
    protocol: str,
    workload_label: str,
    workload_name: str,
    quantile: float,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile({quantile:.2f}, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="{protocol}", {workload_label}="{workload_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def _latency_quantile_between(
    prom_url: str,
    protocol: str,
    source_workload: str,
    destination_workload: str,
    quantile: float,
    period: str = "1m",
) -> float:
    query = (
        f'histogram_quantile({quantile:.2f}, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="{protocol}", source_workload="{source_workload}", destination_workload="{destination_workload}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def _latency_quantile_mesh(
    prom_url: str,
    protocol: str,
    fixed_label: str,
    fixed_workload: str,
    group_label: str,
    quantile: float,
    period: str = "1m",
) -> dict[str, float]:
    query = (
        f'histogram_quantile({quantile:.2f}, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="{protocol}", {fixed_label}="{fixed_workload}"}}'
        f'[{period}])) by ({group_label}, le))'
    )
    results = query_prometheus_vector(prom_url, query)
    mesh: dict[str, float] = {}
    for item in results:
        key = item.get("metric", {}).get(group_label, "unknown")
        try:
            value = float(item.get("value", [None, "0"])[1])
        except Exception:
            value = 0.0
        mesh[key] = value
    return mesh


# Aggregate P10 as destination/source

def get_http_latency_p10_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    return _latency_quantile_scalar(prom_url, "http", "destination_workload", deployment_name, 0.10, period)


def get_grpc_latency_p10_as_dst(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    return _latency_quantile_scalar(prom_url, "grpc", "destination_workload", deployment_name, 0.10, period)


def get_http_latency_p10_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    return _latency_quantile_scalar(prom_url, "http", "source_workload", deployment_name, 0.10, period)


def get_grpc_latency_p10_as_src(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    return _latency_quantile_scalar(prom_url, "grpc", "source_workload", deployment_name, 0.10, period)


# Edge P10 source -> destination

def get_http_latency_p10_between(prom_url: str, source_workload: str, destination_workload: str, period: str = "1m") -> float:
    return _latency_quantile_between(prom_url, "http", source_workload, destination_workload, 0.10, period)


def get_grpc_latency_p10_between(prom_url: str, source_workload: str, destination_workload: str, period: str = "1m") -> float:
    return _latency_quantile_between(prom_url, "grpc", source_workload, destination_workload, 0.10, period)


# Mesh P10 views

def get_http_latency_p10_mesh_as_dst(prom_url: str, destination_workload: str, period: str = "1m") -> dict[str, float]:
    return _latency_quantile_mesh(prom_url, "http", "destination_workload", destination_workload, "source_workload", 0.10, period)


def get_grpc_latency_p10_mesh_as_dst(prom_url: str, destination_workload: str, period: str = "1m") -> dict[str, float]:
    return _latency_quantile_mesh(prom_url, "grpc", "destination_workload", destination_workload, "source_workload", 0.10, period)


def get_http_latency_p10_mesh_as_src(prom_url: str, source_workload: str, period: str = "1m") -> dict[str, float]:
    return _latency_quantile_mesh(prom_url, "http", "source_workload", source_workload, "destination_workload", 0.10, period)


def get_grpc_latency_p10_mesh_as_src(prom_url: str, source_workload: str, period: str = "1m") -> dict[str, float]:
    return _latency_quantile_mesh(prom_url, "grpc", "source_workload", source_workload, "destination_workload", 0.10, period)

