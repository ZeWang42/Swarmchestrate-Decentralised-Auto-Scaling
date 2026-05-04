SERVER_BASE_URL = "http://35.179.164.93:31504"
BOOKINFO_HOST = "http://35.179.164.93:31727"
NAMESPACE = "default"

WORKLOAD_NAME = ["wiki_load"]

AUTOSCALER_SETTINGS = [
        {
        "autoscaler_name": "customDAS",
        "config": {
            "image": "zewang42/customdas-autoscaler:latest",
            "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
            "interval": 30,
            #"cooldown_seconds": 30,

            # existing DAS thresholds
            "alpha_down_threshold": 30,
            "tau_min": 60,
            "tau_max": 80,
            "beta_up_threshold": 95,
            "min_replicas": 1,
            "max_replicas": 10,

            # customDAS P2P settings
            "p2p_hub_deployment": "productpage-v1",
            "p2p_hub_port": 5000,
        },
    },
        {
        "autoscaler_name": "das",
        "config": {
            "image": "zewang42/das-autoscaler:latest",
            "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
            "interval": 30,
            "cooldown_seconds": 30,
            "alpha_down_threshold": 30,
            "tau_min": 60,
            "tau_max": 80,
            "beta_up_threshold": 95,
            "min_replicas": 1,
            "max_replicas": 10,
        },
    },
        {
        "autoscaler_name": "default_cpu",
        "config": {
            "average_cpu_utilization": 80,
            "min_replicas": 1,
            "max_replicas": 10,
        },
    },
]


DURATION_SECONDS = 60 * 2
MONITOR_INTERVAL = 5
PROM_URL = "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query"

LOCUST_FILE = "load/book-info/wiki_locustfile.py"
TMP_DIR = "tmp"
WAIT_BETWEEN_EXPERIMENTS_SECONDS = 20
