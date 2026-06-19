# Example experiment config for running PBScaler with Online Boutique.
# Replace your AUTOSCALER_SETTINGS block with this.

AUTOSCALER_SETTINGS = [
    {
        "autoscaler_name": "pbscaler",
        "deployment_names": APP["deployment_names"],
        "config": {
            "image": "proactivellmbasedproject/pbscaler-boutique:latest",
            "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090",
            "kubeconfig_secret": "pbscaler-kubeconfig",
            "slo_ms": 500,
            "duration_seconds": 1200,
            "num_services": len(APP["deployment_names"]),
            "min_replicas": 1,
            "max_replicas": 10,
            "app_name": APP_NAME,
            "root_service": APP["root_service"],
        },
    },
]
