from __future__ import annotations

from kubernetes import client

#from monitoring.monitor import Monitor
from utils.parsing import parse_cpu_to_millicores, parse_memory_to_mib

"""
LISTING
"""

"""
GETTING RESOURCE USAGE
"""

"""
GETTING UTILISATION PERCENTAGES
"""

def _get_deployment_selector(
    apps_api: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
) -> dict[str, str]:
    try:
        dep = apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
        )
        return dep.spec.selector.match_labels or {}
    except Exception:
        return {}

def list_deployment_pods(
    core_api: client.CoreV1Api,
    apps_api: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
):

    """
        list pods for a deployment
    """
    match_labels = _get_deployment_selector(apps_api, namespace, deployment_name)
    if not match_labels:
        return []

    label_selector = ",".join(f"{k}={v}" for k, v in match_labels.items())

    try:
        pod_list = core_api.list_namespaced_pod(
            namespace=namespace,
            label_selector=label_selector,
        )
        return pod_list.items
    except Exception:
        return []
    
def list_requested_cpu_per_pod_m(
    apps_api: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
) -> list[int]:
    """
    Return a list of requested CPU values (in millicores) for each container
    defined in the deployment pod template.
    """
    try:
        dep = apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
        )
    except Exception:
        return []

    requested_cpu_m_list: list[int] = []

    containers = dep.spec.template.spec.containers or []
    for container in containers:
        resources = container.resources
        if not resources or not resources.requests:
            requested_cpu_m_list.append(0)
            continue

        cpu_req = resources.requests.get("cpu")
        requested_cpu_m_list.append(
            parse_cpu_to_millicores(cpu_req) if cpu_req else 0
        )

    return requested_cpu_m_list


def list_requested_mem_per_pod_mib(
    apps_api: client.AppsV1Api,
    namespace: str,
    deployment_name: str,
) -> list[int]:
    """
    Return a list of requested memory values (in MiB) for each container
    defined in the deployment pod template.
    """
    try:
        dep = apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
        )
    except Exception:
        return []

    requested_mem_mib_list: list[int] = []

    containers = dep.spec.template.spec.containers or []
    for container in containers:
        resources = container.resources
        if not resources or not resources.requests:
            requested_mem_mib_list.append(0)
            continue

        mem_req = resources.requests.get("memory")
        requested_mem_mib_list.append(
            parse_memory_to_mib(mem_req) if mem_req else 0
        )

    return requested_mem_mib_list


def _get_pod_metrics_map(
    custom_api: client.CustomObjectsApi,
    namespace: str,
) -> dict[str, dict]:

    """
        get pod metrics map:
        {
            "pod_name_1": 
                "containers": [{ ... container metrics ... }],
            "pod_name_2":
                "containers": [{ ... container metrics ... }],
            ...
        }
    """
    try:
        metrics = custom_api.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods",
        )
    except Exception:
        return {}

    result: dict[str, dict] = {}
    for item in metrics.get("items", []):
        pod_name = item.get("metadata", {}).get("name", "")
        if pod_name:
            result[pod_name] = item
    return result

def get_node_resource_usage(
    custom_api: client.CustomObjectsApi,
    node_name: str,
) -> tuple[int, int]:
    try:
        metric = custom_api.get_cluster_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            plural="nodes",
            name=node_name,
        )
    except Exception:
        return 0, 0

    usage = metric.get("usage", {})
    cpu_m = parse_cpu_to_millicores(usage.get("cpu", "0"))
    mem_mib = parse_memory_to_mib(usage.get("memory", "0Ki"))
    return cpu_m, mem_mib

def get_deployment_resource_usage(
    core_api: client.CoreV1Api,
    apps_api: client.AppsV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    deployment_name: str,
) -> tuple[int, int, int]:

    """
        get total resource usage (cpu, memory, count) for a deployment by summing up its pods' usage
    """
    pods = list_deployment_pods(core_api, apps_api, namespace, deployment_name)
    if not pods:
        return 0, 0, 0

    matched_pods = {
        pod.metadata.name
        for pod in pods
        if pod.metadata and pod.metadata.name
    }

    running_pods = sum(
        1 for pod in pods if (pod.status.phase or "") == "Running"
    )

    metrics_map = _get_pod_metrics_map(custom_api, namespace)

    cpu_m = 0
    mem_mib = 0

    for pod_name in matched_pods:
        pod_metric = metrics_map.get(pod_name)
        if not pod_metric:
            continue

        for container_metrics in pod_metric.get("containers", []):
            usage = container_metrics.get("usage", {})
            cpu_m += parse_cpu_to_millicores(usage.get("cpu", "0"))
            mem_mib += parse_memory_to_mib(usage.get("memory", "0Ki"))

    return cpu_m, mem_mib, running_pods

def get_pod_resource_usage(
    custom_api: client.CustomObjectsApi,
    namespace: str,
    pod_name: str,
) -> tuple[int, int]:

    """
        get pod resource usage (cpu, memory) by pod name
    """
    metrics_map = _get_pod_metrics_map(custom_api, namespace)
    pod_metric = metrics_map.get(pod_name)
    if not pod_metric:
        return 0, 0

    cpu_m = 0
    mem_mib = 0

    for container_metrics in pod_metric.get("containers", []):
        usage = container_metrics.get("usage", {})
        cpu_m += parse_cpu_to_millicores(usage.get("cpu", "0"))
        mem_mib += parse_memory_to_mib(usage.get("memory", "0Ki"))

    return cpu_m, mem_mib

def get_node_utilisation_percent(
    core_api: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    node_name: str,
) -> tuple[float, float]:
    try:
        node_obj = core_api.read_node(name=node_name)
        alloc_cpu_m = parse_cpu_to_millicores(
            node_obj.status.allocatable.get("cpu", "0")
        )
        alloc_mem_mib = parse_memory_to_mib(
            node_obj.status.allocatable.get("memory", "0Ki")
        )
    except Exception:
        return 0.0, 0.0

    used_cpu_m, used_mem_mib = get_node_resource_usage(custom_api, node_name)

    cpu_pct = (used_cpu_m / alloc_cpu_m * 100.0) if alloc_cpu_m > 0 else 0.0
    mem_pct = (used_mem_mib / alloc_mem_mib * 100.0) if alloc_mem_mib > 0 else 0.0
    return cpu_pct, mem_pct

def get_deployment_utilisation_percent(
    apps_api: client.AppsV1Api,
    core_api: client.CoreV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    deployment_name: str,
) -> tuple[float, float]:
    try:
        dep = apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
        )
    except Exception:
        return 0.0, 0.0

    used_cpu_m, used_mem_mib, running_pods = get_deployment_resource_usage(
        core_api,
        apps_api,
        custom_api,
        namespace,
        deployment_name,
    )

    if running_pods <= 0:
        return 0.0, 0.0

    requested_cpu_per_pod_m = 0
    requested_mem_per_pod_mib = 0

    containers = dep.spec.template.spec.containers or []
    for container in containers:
        resources = container.resources
        if not resources or not resources.requests:
            continue

        cpu_req = resources.requests.get("cpu")
        mem_req = resources.requests.get("memory")

        if cpu_req:
            requested_cpu_per_pod_m += parse_cpu_to_millicores(cpu_req)
        if mem_req:
            requested_mem_per_pod_mib += parse_memory_to_mib(mem_req)

    requested_cpu_m = requested_cpu_per_pod_m * running_pods
    requested_mem_mib = requested_mem_per_pod_mib * running_pods

    cpu_pct = (used_cpu_m / requested_cpu_m * 100.0) if requested_cpu_m > 0 else 0.0
    mem_pct = (used_mem_mib / requested_mem_mib * 100.0) if requested_mem_mib > 0 else 0.0

    return cpu_pct, mem_pct

def get_pod_utilisation_percent(
    apps_api: client.AppsV1Api,
    custom_api: client.CustomObjectsApi,
    namespace: str,
    deployment_name: str,
    pod_name: str,
) -> tuple[float, float]:
    """
    Return CPU and memory utilisation percentages for one pod, relative to
    the resource requests defined in the deployment template.

    Returns:
        (cpu_pct, mem_pct)
    """
    try:
        dep = apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
        )
    except Exception:
        return 0.0, 0.0

    used_cpu_m, used_mem_mib = get_pod_resource_usage(
        custom_api,
        namespace,
        pod_name,
    )

    requested_cpu_m = 0
    requested_mem_mib = 0

    containers = dep.spec.template.spec.containers or []
    for container in containers:
        resources = container.resources
        if not resources or not resources.requests:
            continue

        cpu_req = resources.requests.get("cpu")
        mem_req = resources.requests.get("memory")

        if cpu_req:
            requested_cpu_m += parse_cpu_to_millicores(cpu_req)
        if mem_req:
            requested_mem_mib += parse_memory_to_mib(mem_req)

    cpu_pct = (used_cpu_m / requested_cpu_m * 100.0) if requested_cpu_m > 0 else 0.0
    mem_pct = (used_mem_mib / requested_mem_mib * 100.0) if requested_mem_mib > 0 else 0.0

    return cpu_pct, mem_pct