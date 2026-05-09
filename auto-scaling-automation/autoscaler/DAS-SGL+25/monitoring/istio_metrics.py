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

def get_http_rpm(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_rpm(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'sum(rate(istio_requests_total'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) * 60'
    )
    return query_prometheus_scalar(prom_url, query)


def get_http_latency_p95(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="http", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
    )
    return query_prometheus_scalar(prom_url, query)


def get_grpc_latency_p95(prom_url: str, deployment_name: str, period: str = "1m") -> float:
    query = (
        f'histogram_quantile(0.95, '
        f'sum(rate(istio_request_duration_milliseconds_bucket'
        f'{{request_protocol="grpc", destination_workload="{deployment_name}"}}'
        f'[{period}])) by (le))'
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

def get_http_rpm_mesh(
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


def get_grpc_rpm_mesh(
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


def get_http_latency_mesh(
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


def get_grpc_latency_mesh(
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