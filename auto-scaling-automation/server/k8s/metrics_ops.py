
from __future__ import annotations

import requests
from kubernetes import client

from config import ALL_KNOWN_DEPLOYMENTS
from utils.parsing import parse_cpu_to_millicores, parse_memory_to_mib

def get_deployments(namespace: str) -> list[str]:
    apps_api = client.AppsV1Api()
    resp = apps_api.list_namespaced_deployment(namespace=namespace)
    names = [item.metadata.name for item in resp.items if item.metadata and item.metadata.name]
    return [name for name in names if name in ALL_KNOWN_DEPLOYMENTS]

def get_nodes() -> list[str]:
    core_api = client.CoreV1Api()
    resp = core_api.list_node()
    return [item.metadata.name for item in resp.items if item.metadata and item.metadata.name]

def service_pod_metrics(namespace: str, deployment_name: str) -> tuple[int, int, int]:
    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()

    cpu_m = 0
    mem_mib = 0
    running_pods = 0

    try:
        dep = apps_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        match_labels = dep.spec.selector.match_labels or {}
    except Exception:
        return 0, 0, 0

    label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())
    if not label_selector:
        return 0, 0, 0

    try:
        pod_list = core_api.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        matched_pods = {pod.metadata.name for pod in pod_list.items if pod.metadata and pod.metadata.name}
        running_pods = sum(1 for pod in pod_list.items if (pod.status.phase or "") == "Running")
    except Exception:
        return 0, 0, 0

    try:
        metrics = custom_api.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods",
        )
    except Exception:
        return 0, 0, running_pods

    for item in metrics.get("items", []):
        pod_name = item.get("metadata", {}).get("name", "")
        if pod_name not in matched_pods:
            continue
        for container_metrics in item.get("containers", []):
            usage = container_metrics.get("usage", {})
            cpu_m += parse_cpu_to_millicores(usage.get("cpu", "0"))
            mem_mib += parse_memory_to_mib(usage.get("memory", "0Ki"))
    return cpu_m, mem_mib, running_pods

def node_usage(node_name: str) -> tuple[int, int]:
    custom_api = client.CustomObjectsApi()
    try:
        metric = custom_api.get_cluster_custom_object(group="metrics.k8s.io", version="v1beta1", plural="nodes", name=node_name)
    except Exception:
        return 0, 0
    usage = metric.get("usage", {})
    return parse_cpu_to_millicores(usage.get("cpu", "0")), parse_memory_to_mib(usage.get("memory", "0Ki"))

def node_utilization_percent(node_name: str) -> tuple[float, float]:
    core_api = client.CoreV1Api()
    custom_api = client.CustomObjectsApi()
    try:
        node_obj = core_api.read_node(name=node_name)
        alloc_cpu_m = parse_cpu_to_millicores(node_obj.status.allocatable.get("cpu", "0"))
        alloc_mem_mib = parse_memory_to_mib(node_obj.status.allocatable.get("memory", "0Ki"))
    except Exception:
        return 0.0, 0.0
    try:
        metric = custom_api.get_cluster_custom_object(group="metrics.k8s.io", version="v1beta1", plural="nodes", name=node_name)
        usage = metric.get("usage", {})
        used_cpu_m = parse_cpu_to_millicores(usage.get("cpu", "0"))
        used_mem_mib = parse_memory_to_mib(usage.get("memory", "0Ki"))
    except Exception:
        return 0.0, 0.0
    cpu_pct = (used_cpu_m / alloc_cpu_m * 100.0) if alloc_cpu_m > 0 else 0.0
    mem_pct = (used_mem_mib / alloc_mem_mib * 100.0) if alloc_mem_mib > 0 else 0.0
    return cpu_pct, mem_pct

def query_prometheus(prom_url: str, query: str) -> float:
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
