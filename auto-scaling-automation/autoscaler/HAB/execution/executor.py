from __future__ import annotations

from kubernetes import client

from .types import ScaleResult


class Executor:
    """
    Small public execution API for scaling Kubernetes deployments.
    """

    def __init__(self, namespace: str):
        self.namespace = namespace
        self.apps_api = client.AppsV1Api()

    def get_replicas(self, deployment_name: str) -> int:
        """
        Return the current desired replica count of a deployment.
        """
        dep = self.apps_api.read_namespaced_deployment(
            name=deployment_name,
            namespace=self.namespace,
        )
        return dep.spec.replicas or 0

    def set_replicas(self, deployment_name: str, replicas: int) -> ScaleResult:
        """
        Set the desired replica count of a deployment.
        """
        if replicas < 0:
            replicas = 0

        previous = self.get_replicas(deployment_name)

        self.apps_api.patch_namespaced_deployment_scale(
            name=deployment_name,
            namespace=self.namespace,
            body={"spec": {"replicas": replicas}},
        )

        return ScaleResult(
            deployment_name=deployment_name,
            previous_replicas=previous,
            desired_replicas=replicas,
            applied=(previous != replicas),
        )

    def scale_by(
        self,
        deployment_name: str,
        delta: int,
        min_replicas: int = 1,
        max_replicas: int | None = None,
    ) -> ScaleResult:
        """
        Increase or decrease replicas relative to current count.
        """
        current = self.get_replicas(deployment_name)
        desired = current + delta

        if desired < min_replicas:
            desired = min_replicas

        if max_replicas is not None and desired > max_replicas:
            desired = max_replicas

        return self.set_replicas(deployment_name, desired)
