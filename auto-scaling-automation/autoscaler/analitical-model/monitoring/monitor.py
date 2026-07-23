from __future__ import annotations

from kubernetes import client

from monitoring.k8s_metrics import (
    list_deployment_pods as _list_deployment_pods,
    list_requested_cpu_per_pod_m as _list_requested_cpu_per_pod_m,
    list_requested_mem_per_pod_mib as _list_requested_mem_per_pod_mib,
    get_node_resource_usage,
    get_deployment_resource_usage,
    get_pod_resource_usage,
    get_node_utilisation_percent,
    get_deployment_utilisation_percent,
    get_pod_utilisation_percent,
)

from monitoring.istio_metrics import (
    check_prometheus,

    get_http_rpm_as_src,
    get_grpc_rpm_as_src,
    get_http_latency_as_src,
    get_grpc_latency_as_src,

    get_http_latency_p95_as_src,
    get_grpc_latency_p95_as_src,

    get_http_rpm_as_dst,
    get_grpc_rpm_as_dst,
    get_http_latency_as_dst,
    get_grpc_latency_as_dst,

    get_grpc_latency_p50_as_dst,
    get_http_latency_p50_as_dst,
    get_http_latency_p95_as_dst,
    get_grpc_latency_p95_as_dst,

    get_http_rpm_between,
    get_grpc_rpm_between,
    get_http_latency_p95_between,
    get_grpc_latency_p95_between,

    get_http_rpm_mesh_as_dst,
    get_grpc_rpm_mesh_as_dst,
    get_http_latency_mesh_as_dst,
    get_grpc_latency_mesh_as_dst,
    get_http_latency_p95_mesh_as_dst,
    get_grpc_latency_p95_mesh_as_dst,

    get_http_rpm_mesh_as_src,
    get_grpc_rpm_mesh_as_src,
    get_http_latency_mesh_as_src,
    get_grpc_latency_mesh_as_src,
    get_http_latency_p95_mesh_as_src,
    get_grpc_latency_p95_mesh_as_src,
)

from monitoring.types import (
    NodeResources,
    DeploymentResources,
    PodResources,
    NodeUtilisation,
    DeploymentUtilisation,
    PodUtilisation,
)


class Monitor:
    """
    Small public monitoring API for:
    - Kubernetes metrics-server values
    - Istio/Prometheus aggregate values
    - Istio/Prometheus mesh values
    """

    def __init__(self, namespace: str, prom_url: str, prometheus_period: str = "1m"):
        self.namespace = namespace
        self.prom_url = prom_url
        self.prometheus_period = prometheus_period

        self.core_api = client.CoreV1Api()
        self.apps_api = client.AppsV1Api()
        self.custom_api = client.CustomObjectsApi()

        self.prometheus_available = check_prometheus(prom_url)

    # ------------------------------------------------------------------
    # Kubernetes resource listing
    # ------------------------------------------------------------------

    def list_deployment_pods(self, deployment_name: str) -> list[client.V1Pod]:
        return _list_deployment_pods(
            self.core_api,
            self.apps_api,
            self.namespace,
            deployment_name,
        )

    def get_requested_cpu_per_pod_m(self, deployment_name: str) -> int:
        """
        Get total requested CPU per pod for a deployment, in millicores.
        """
        return sum(
            _list_requested_cpu_per_pod_m(
                self.apps_api,
                self.namespace,
                deployment_name,
            )
        )

    def get_requested_mem_per_pod_mib(self, deployment_name: str) -> int:
        """
        Get total requested memory per pod for a deployment, in MiB.
        """
        return sum(
            _list_requested_mem_per_pod_mib(
                self.apps_api,
                self.namespace,
                deployment_name,
            )
        )

    # ------------------------------------------------------------------
    # Kubernetes resource metrics
    # ------------------------------------------------------------------

    def get_node_resources(self, node_name: str) -> NodeResources:
        """
        Get node resource usage (cpu, memory).
        """
        cpu_m, mem_mib = get_node_resource_usage(
            self.custom_api,
            node_name,
        )
        return NodeResources(cpu_m=cpu_m, mem_mib=mem_mib)

    def get_deployment_resources(self, deployment_name: str) -> DeploymentResources:
        """
        Get deployment resource usage (cpu, memory, and pod count).
        """
        cpu_m, mem_mib, running_pods = get_deployment_resource_usage(
            self.core_api,
            self.apps_api,
            self.custom_api,
            self.namespace,
            deployment_name,
        )
        return DeploymentResources(
            cpu_m=cpu_m,
            mem_mib=mem_mib,
            running_pods=running_pods,
        )

    def get_pod_resources(self, pod_name: str) -> PodResources:
        """
        Get pod resource usage (cpu, memory).
        """
        cpu_m, mem_mib = get_pod_resource_usage(
            self.custom_api,
            self.namespace,
            pod_name,
        )
        return PodResources(cpu_m=cpu_m, mem_mib=mem_mib)

    def get_node_utilisation(self, node_name: str) -> NodeUtilisation:
        """
        Get node utilisation (cpu, memory) in percentage.
        """
        cpu_pct, mem_pct = get_node_utilisation_percent(
            self.core_api,
            self.custom_api,
            node_name,
        )
        return NodeUtilisation(cpu_pct=cpu_pct, mem_pct=mem_pct)

    def get_deployment_utilisation(self, deployment_name: str) -> DeploymentUtilisation:
        """
        Get deployment utilisation (CPU, memory) in percentage.
        """
        cpu_pct, mem_pct = get_deployment_utilisation_percent(
            self.apps_api,
            self.core_api,
            self.custom_api,
            self.namespace,
            deployment_name,
        )
        return DeploymentUtilisation(cpu_pct=cpu_pct, mem_pct=mem_pct)

    def get_pod_utilisation(self, deployment_name: str, pod_name: str) -> PodUtilisation:
        """
        Get pod utilisation (CPU, memory) in percentage.
        """
        cpu_pct, mem_pct = get_pod_utilisation_percent(
            self.apps_api,
            self.custom_api,
            self.namespace,
            deployment_name,
            pod_name,
        )
        return PodUtilisation(cpu_pct=cpu_pct, mem_pct=mem_pct)

    def get_pod_count(self, deployment_name: str) -> int:
        return self.get_deployment_resources(deployment_name).running_pods

    # ------------------------------------------------------------------
    # Istio aggregate metrics as source workload
    # ------------------------------------------------------------------

    def get_http_rpm_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_rpm_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_rpm_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_rpm_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_http_latency_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_http_latency_p95_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_p95_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p95_as_src(self, source_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_p95_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    # ------------------------------------------------------------------
    # Istio aggregate metrics as destination workload
    # ------------------------------------------------------------------

    def get_http_rpm_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_rpm_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_rpm_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_rpm_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_http_latency_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_http_latency_p50_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_p50_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p50_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_p50_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )


    def get_http_latency_p95_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_p95_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p95_as_dst(self, destination_workload: str) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_p95_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    # ------------------------------------------------------------------
    # Backward-compatible aliases
    # These treat the workload as destination, matching the old behavior.
    # ------------------------------------------------------------------

    def get_http_rpm(self, deployment_name: str) -> float:
        return self.get_http_rpm_as_dst(deployment_name)

    def get_grpc_rpm(self, deployment_name: str) -> float:
        return self.get_grpc_rpm_as_dst(deployment_name)

    def get_http_latency(self, deployment_name: str) -> float:
        return self.get_http_latency_as_dst(deployment_name)

    def get_grpc_latency(self, deployment_name: str) -> float:
        return self.get_grpc_latency_as_dst(deployment_name)

    def get_http_latency_p95(self, deployment_name: str) -> float:
        return self.get_http_latency_p95_as_dst(deployment_name)

    def get_grpc_latency_p95(self, deployment_name: str) -> float:
        return self.get_grpc_latency_p95_as_dst(deployment_name)

    # ------------------------------------------------------------------
    # Istio mesh edge metrics: source -> destination
    # ------------------------------------------------------------------

    def get_http_rpm_between(
        self,
        source_workload: str,
        destination_workload: str,
    ) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_rpm_between(
            self.prom_url,
            source_workload,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_rpm_between(
        self,
        source_workload: str,
        destination_workload: str,
    ) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_rpm_between(
            self.prom_url,
            source_workload,
            destination_workload,
            self.prometheus_period,
        )

    def get_http_latency_p95_between(
        self,
        source_workload: str,
        destination_workload: str,
    ) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_http_latency_p95_between(
            self.prom_url,
            source_workload,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p95_between(
        self,
        source_workload: str,
        destination_workload: str,
    ) -> float:
        if not self.prometheus_available:
            return 0.0
        return get_grpc_latency_p95_between(
            self.prom_url,
            source_workload,
            destination_workload,
            self.prometheus_period,
        )

    # ------------------------------------------------------------------
    # Istio mesh views for one destination workload
    # Returns dict[source_workload] = value
    # ------------------------------------------------------------------

    def get_http_rpm_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_rpm_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_rpm_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_rpm_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_http_latency_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_latency_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_latency_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_http_latency_p95_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_latency_p95_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p95_mesh_as_dst(self, destination_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_latency_p95_mesh_as_dst(
            self.prom_url,
            destination_workload,
            self.prometheus_period,
        )

    # ------------------------------------------------------------------
    # Istio mesh views for one source workload
    # Returns dict[destination_workload] = value
    # ------------------------------------------------------------------

    def get_http_rpm_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_rpm_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_rpm_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_rpm_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_http_latency_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_latency_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_latency_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_http_latency_p95_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_http_latency_p95_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    def get_grpc_latency_p95_mesh_as_src(self, source_workload: str) -> dict[str, float]:
        if not self.prometheus_available:
            return {}
        return get_grpc_latency_p95_mesh_as_src(
            self.prom_url,
            source_workload,
            self.prometheus_period,
        )

    # ------------------------------------------------------------------
    # Backward-compatible mesh aliases
    # These preserve the old semantics: fixed destination, grouped by source.
    # ------------------------------------------------------------------

    def get_http_rpm_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_http_rpm_mesh_as_dst(destination_workload)

    def get_grpc_rpm_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_grpc_rpm_mesh_as_dst(destination_workload)

    def get_http_latency_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_http_latency_mesh_as_dst(destination_workload)

    def get_grpc_latency_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_grpc_latency_mesh_as_dst(destination_workload)

    def get_http_latency_p95_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_http_latency_p95_mesh_as_dst(destination_workload)

    def get_grpc_latency_p95_mesh(self, destination_workload: str) -> dict[str, float]:
        return self.get_grpc_latency_p95_mesh_as_dst(destination_workload)
    

    # ------------------------------------------------------------------
    # get upstreams according to destination workloads
    # ------------------------------------------------------------------
    def get_upstreams(self, destination_workload: str) -> list[str]:
        if not self.prometheus_available:
            return []

        http = self.get_http_rpm_mesh_as_dst(destination_workload) or {}
        grpc = self.get_grpc_rpm_mesh_as_dst(destination_workload) or {}

        # merge keys
        upstreams = set(http.keys()) | set(grpc.keys())

        # remove self if present
        upstreams.discard(destination_workload)

        return list(upstreams)
    
    # ------------------------------------------------------------------
    # get downstreams according to source workloads
    # ------------------------------------------------------------------
    def get_downstreams(self, source_workload: str) -> list[str]:
        if not self.prometheus_available:
            return []

        http = self.get_http_rpm_mesh_as_src(source_workload) or {}
        grpc = self.get_grpc_rpm_mesh_as_src(source_workload) or {}

        # merge downstream services
        downstreams = set(http.keys()) | set(grpc.keys())

        # remove self if present
        downstreams.discard(source_workload)

        return list(downstreams)