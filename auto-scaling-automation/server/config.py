from pathlib import Path
import os

DEFAULT_NAMESPACE = os.getenv("APP_NAMESPACE", "default")

BOOKINFO_APP_NAME = "bookinfo"
ONLINEBOUTIQUE_APP_NAME = "onlineboutique"

BOOKINFO_MANIFEST = os.getenv("BOOKINFO_MANIFEST", "/app/manifests/applications/bookinfo/bookinfo.yaml")
BOOKINFO_GATEWAY_MANIFEST = os.getenv("BOOKINFO_GATEWAY_MANIFEST", "/app/manifests/applications/bookinfo/bookinfo-gateway.yaml")
ONLINEBOUTIQUE_MANIFEST = os.getenv("ONLINEBOUTIQUE_MANIFEST", "/app/manifests/applications/onlineboutique/onlineboutique.yaml")
ONLINEBOUTIQUE_GATEWAY_MANIFEST = os.getenv("ONLINEBOUTIQUE_GATEWAY_MANIFEST", "/app/manifests/applications/onlineboutique/onlineboutique-gateway.yaml")

PROM_URL = os.getenv("PROM_URL", "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query")
MONITOR_LOG_DIR = Path(os.getenv("MONITOR_LOG_DIR", "/app/logs"))
AUTOSCALER_MANIFESTS_DIR = Path(os.getenv("AUTOSCALER_MANIFESTS_DIR", "/app/manifests/autoscalers"))

BOOKINFO_DEPLOYMENTS = [
    "details-v1",
    "productpage-v1",
    "ratings-v1",
    "reviews-v1",
    "reviews-v2",
    "reviews-v3",
]

BOOKINFO_SERVICES = ["details", "productpage", "ratings", "reviews"]

ONLINEBOUTIQUE_DEPLOYMENTS = [
    "emailservice",
    "checkoutservice",
    "recommendationservice",
    "frontend",
    "paymentservice",
    "productcatalogservice",
    "cartservice",
    "currencyservice",
    "shippingservice",
    "redis-cart",
    "adservice",
]

ONLINEBOUTIQUE_SERVICES = ONLINEBOUTIQUE_DEPLOYMENTS.copy()

APPLICATIONS = {
    BOOKINFO_APP_NAME: {
        "name": BOOKINFO_APP_NAME,
        "manifest": BOOKINFO_MANIFEST,
        "gateway_manifest": BOOKINFO_GATEWAY_MANIFEST,
        "deployments": BOOKINFO_DEPLOYMENTS,
        "services": BOOKINFO_SERVICES,
        "latency_deployment": "productpage-v1",
    },
    ONLINEBOUTIQUE_APP_NAME: {
        "name": ONLINEBOUTIQUE_APP_NAME,
        "manifest": ONLINEBOUTIQUE_MANIFEST,
        "gateway_manifest": ONLINEBOUTIQUE_GATEWAY_MANIFEST,
        "deployments": ONLINEBOUTIQUE_DEPLOYMENTS,
        "services": ONLINEBOUTIQUE_SERVICES,
        "latency_deployment": "frontend",
    },
}

def latency_deployments() -> set[str]:
    return {
        app["latency_deployment"]
        for app in APPLICATIONS.values()
        if app.get("latency_deployment")
    }
SUPPORTED_APP_NAMES = set(APPLICATIONS.keys())
ALL_KNOWN_DEPLOYMENTS = sorted({deployment for app in APPLICATIONS.values() for deployment in app["deployments"]})

AUTOSCALER_NAME_ALIASES = {
    "cpu": "default_cpu",
    "default-cpu": "default_cpu",
    "custom": "das",
    "customdas": "customdas",
    "custom-das": "customdas",
    "custom_das": "customdas",
    "customdascpu": "customdas-cpu",
    "customdas_cpu": "customdas-cpu",
    "customdas-cpu": "customdas-cpu",
    "customdas cpu": "customdas-cpu",
    "customdascpuqueue": "customdas-cpu-queue",
    "customdas_cpu_queue": "customdas-cpu-queue",
    "customdas-cpu-queue": "customdas-cpu-queue",
    "customdas cpu queue": "customdas-cpu-queue",
    "dadqn": "dadqn",
    "da-dqn": "dadqn",
    "da_dqn": "dadqn",
    "da dqn": "dadqn",
    "pbscaler": "pbscaler",
    "pb-scaler": "pbscaler",
    "pb_scaler": "pbscaler",
    "pb scaler": "pbscaler",

    "hab": "hab",
    "holistic": "hab",
    "hab-autoscaler": "hab",
    "hab_autoscaler": "hab",
}
