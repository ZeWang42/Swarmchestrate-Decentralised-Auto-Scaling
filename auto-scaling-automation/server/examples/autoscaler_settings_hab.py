# Example HAB autoscaler setting for Online Boutique.
# HAB is an application-level scheduler, so it manages the whole calibrated
# Online Boutique service vector rather than one controller per microservice.

AUTOSCALER_SETTINGS = [
    {
        "autoscaler_name": "hab",
        "deployment_names": APP["deployment_names"],
        "config": {
            "image": "zewang42/hab-autoscaler",
            "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
            "interval": 15,
            "cooldown_seconds": 30,
            "root_service": APP["root_service"],
            "lambda_base_rps": 139.11,
            "phi_base": 3.37,
            "r_up_ms": 500,
            "r_low_ms": 400,
            "hab_post_proportional_wait_seconds": 60,
            "hab_stabilization_seconds": 60,
            "hab_exploratory_enabled": True,
            "hab_exploratory_max_steps": 3,
            "hab_stable_lambda_rel_delta": 0.10,
            "hab_scale_down_enabled": True,
            "min_replicas": 1,
            "max_replicas": 10,
        },
    },
]
