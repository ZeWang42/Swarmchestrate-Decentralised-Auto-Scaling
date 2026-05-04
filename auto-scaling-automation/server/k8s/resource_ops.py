from __future__ import annotations

from pathlib import Path
import yaml
from kubernetes import client, utils
from kubernetes.client import ApiClient
from kubernetes.client.exceptions import ApiException


def apply_yaml(path: str, namespace: str) -> None:
    api_client = ApiClient()
    utils.create_from_yaml(api_client, path, namespace=namespace, verbose=False)


def _create_or_patch(obj: dict, namespace: str) -> None:
    kind = obj.get("kind")
    metadata = obj.get("metadata", {})
    name = metadata.get("name")
    obj_namespace = metadata.get("namespace") or namespace

    if not kind or not name:
        raise ValueError("Object must define kind and metadata.name")

    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    autoscaling_api = client.AutoscalingV2Api()
    rbac_api = client.RbacAuthorizationV1Api()

    try:
        if kind == "ServiceAccount":
            core_api.create_namespaced_service_account(namespace=obj_namespace, body=obj)
        elif kind == "Role":
            rbac_api.create_namespaced_role(namespace=obj_namespace, body=obj)
        elif kind == "RoleBinding":
            rbac_api.create_namespaced_role_binding(namespace=obj_namespace, body=obj)
        elif kind == "Deployment":
            apps_api.create_namespaced_deployment(namespace=obj_namespace, body=obj)
        elif kind == "HorizontalPodAutoscaler":
            autoscaling_api.create_namespaced_horizontal_pod_autoscaler(namespace=obj_namespace, body=obj)
        else:
            api_client = ApiClient()
            utils.create_from_dict(api_client, obj, namespace=obj_namespace, verbose=False)
    except ApiException as exc:
        if exc.status != 409:
            raise

        if kind == "ServiceAccount":
            core_api.patch_namespaced_service_account(name=name, namespace=obj_namespace, body=obj)
        elif kind == "Role":
            rbac_api.patch_namespaced_role(name=name, namespace=obj_namespace, body=obj)
        elif kind == "RoleBinding":
            rbac_api.patch_namespaced_role_binding(name=name, namespace=obj_namespace, body=obj)
        elif kind == "Deployment":
            apps_api.patch_namespaced_deployment(name=name, namespace=obj_namespace, body=obj)
        elif kind == "HorizontalPodAutoscaler":
            autoscaling_api.patch_namespaced_horizontal_pod_autoscaler(name=name, namespace=obj_namespace, body=obj)
        else:
            raise


def apply_objects(objs: list[dict], namespace: str) -> None:
    for obj in objs:
        _create_or_patch(obj, namespace)


def delete_resources_from_yaml(path: str, default_namespace: str) -> list[str]:
    deleted: list[str] = []
    docs = list(yaml.safe_load_all(Path(path).read_text(encoding="utf-8")))

    core_api = client.CoreV1Api()
    apps_api = client.AppsV1Api()
    custom_api = client.CustomObjectsApi()
    autoscaling_api = client.AutoscalingV2Api()

    for doc in docs:
        if not doc:
            continue
        kind = doc.get("kind")
        api_version = doc.get("apiVersion", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name")
        namespace = metadata.get("namespace", default_namespace)

        if not kind or not name:
            continue

        try:
            if kind == "Deployment":
                apps_api.delete_namespaced_deployment(name=name, namespace=namespace)
            elif kind == "DaemonSet":
                apps_api.delete_namespaced_daemon_set(name=name, namespace=namespace)
            elif kind == "Service":
                core_api.delete_namespaced_service(name=name, namespace=namespace)
            elif kind == "ConfigMap":
                core_api.delete_namespaced_config_map(name=name, namespace=namespace)
            elif kind == "Secret":
                core_api.delete_namespaced_secret(name=name, namespace=namespace)
            elif kind == "ServiceAccount":
                core_api.delete_namespaced_service_account(name=name, namespace=namespace)
            elif kind == "HorizontalPodAutoscaler":
                autoscaling_api.delete_namespaced_horizontal_pod_autoscaler(name=name, namespace=namespace)
            elif kind == "ClusterRole":
                client.RbacAuthorizationV1Api().delete_cluster_role(name=name)
            elif kind == "ClusterRoleBinding":
                client.RbacAuthorizationV1Api().delete_cluster_role_binding(name=name)
            elif kind == "Role":
                client.RbacAuthorizationV1Api().delete_namespaced_role(name=name, namespace=namespace)
            elif kind == "RoleBinding":
                client.RbacAuthorizationV1Api().delete_namespaced_role_binding(name=name, namespace=namespace)
            elif kind == "Gateway":
                if api_version.startswith("networking.istio.io/"):
                    custom_api.delete_namespaced_custom_object(
                        group="networking.istio.io",
                        version=api_version.split("/")[1],
                        namespace=namespace,
                        plural="gateways",
                        name=name,
                    )
                elif api_version.startswith("gateway.networking.k8s.io/"):
                    custom_api.delete_namespaced_custom_object(
                        group="gateway.networking.k8s.io",
                        version=api_version.split("/")[1],
                        namespace=namespace,
                        plural="gateways",
                        name=name,
                    )
            elif kind == "HTTPRoute":
                custom_api.delete_namespaced_custom_object(
                    group="gateway.networking.k8s.io",
                    version=api_version.split("/")[1],
                    namespace=namespace,
                    plural="httproutes",
                    name=name,
                )
            elif kind == "VirtualService":
                custom_api.delete_namespaced_custom_object(
                    group="networking.istio.io",
                    version=api_version.split("/")[1],
                    namespace=namespace,
                    plural="virtualservices",
                    name=name,
                )
            else:
                continue
            deleted.append(f"{kind}/{name}")
        except ApiException as exc:
            if exc.status == 404:
                deleted.append(f"{kind}/{name} (already absent)")
            else:
                raise
    return deleted
