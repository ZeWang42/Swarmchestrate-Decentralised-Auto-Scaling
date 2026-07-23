Client autoscaler settings

Use AUTOSCALER_SETTINGS in config/exp_config.py.

Examples:

AUTOSCALER_SETTINGS = [
    {"autoscaler_name": "none", "config": {}},
    {
        "autoscaler_name": "default_cpu",
        "config": {
            "average_cpu_utilization": 20,
            "min_replicas": 1,
            "max_replicas": 10,
        },
    },
    {
        "autoscaler_name": "das",
        "config": {
            "image": "zewang42/das-autoscaler:latest",
            "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
            "interval": 15,
            "cooldown_seconds": 30,
            "alpha_down_threshold": 30,
            "tau_min": 60,
            "tau_max": 80,
            "beta_up_threshold": 90,
            "min_replicas": 1,
            "max_replicas": 10,
        },
    },
]

To target a subset instead of all deployments, add deployment_names to the autoscaler setting.
