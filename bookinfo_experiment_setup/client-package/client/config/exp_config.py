SERVER_BASE_URL = "http://18.175.63.64:8000"
BOOKINFO_HOST = "http://18.175.63.64:8080"
NAMESPACE = "default"

#REQUEST_RATES = [100]
WORKLOAD_NAME = ["wiki_load"]


HPA_SETTINGS = [
  #  {"mode": "none", "target_cpu_utilization": None, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "none", "target_cpu_utilization": None, "min_replicas": 1, "max_replicas": 10},
    {"mode": "cpu", "target_cpu_utilization": 20, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 20, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 20, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 50, "min_replicas": 1, "max_replicas": 10},
#    {"mode": "cpu", "target_cpu_utilization": 50, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 50, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 80, "min_replicas": 1, "max_replicas": 10},
  #  {"mode": "cpu", "target_cpu_utilization": 80, "min_replicas": 1, "max_replicas": 10},
#    {"mode": "cpu", "target_cpu_utilization": 80, "min_replicas": 1, "max_replicas": 10},
#    {"mode": "none", "target_cpu_utilization": None, "min_replicas": 1, "max_replicas": 10},
]

DURATION_SECONDS = 60
MONITOR_INTERVAL = 5
PROM_URL = "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query"

LOCUST_FILE = "load/book-info/wiki_locustfile.py"
TMP_DIR = "tmp"
WAIT_BETWEEN_EXPERIMENTS_SECONDS = 30
