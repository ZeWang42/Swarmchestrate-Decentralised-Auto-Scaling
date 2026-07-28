
from kubernetes import utils

def format_fail_to_create(exc: utils.FailToCreateError) -> str:
    return "; ".join(str(e) for e in exc.api_exceptions)


def build_gateway_hint(namespace: str) -> str:
    return f"Check ingress or gateway exposure for namespace '{namespace}'"


def safe_prefix(value: str) -> str:
    return value.replace("/", "_").replace(" ", "_")
