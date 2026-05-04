SERVER_BASE_URL = "http://18.175.63.64:32177"
BOOKINFO_HOST = "http://18.175.63.64:31649"
NAMESPACE = "default"

WORKLOAD_NAME = ["wiki_load"]

AUTOSCALER_SETTINGS = [
#    {"autoscaler_name": "none", "config": {}},
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
]

DURATION_SECONDS = 60 * 3
MONITOR_INTERVAL = 5
PROM_URL = "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query"

LOCUST_FILE = "load/book-info/wiki_locustfile.py"
TMP_DIR = "tmp"
WAIT_BETWEEN_EXPERIMENTS_SECONDS = 20
