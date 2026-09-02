#APP_NAME = "bookinfo"
APP_NAME = "onlineboutique"

SERVER_IP = "193.225.251.227"
#SERVER_IP = "18.175.57.43"
#SERVER_PORT = "31499"
SERVER_PORT = "30475"
SERVER_BASE_URL = f"http://{SERVER_IP}:{SERVER_PORT}"

NAMESPACE = "default"

APP_CONFIGS = {
    "bookinfo": {
        #"app_port": "31681",
        "app_port": "32014",
        "locust_file": "load/book-info/wiki_locustfile.py",
        "root_service": "productpage-v1",
        "deployment_names": [
            "productpage-v1",
            "details-v1",
            "ratings-v1",
            "reviews-v1",
            "reviews-v2",
            "reviews-v3",
        ],
    },
    "onlineboutique": {
        "app_port": "30894",
        "locust_file": "load/online-boutique/wiki_locustfile.py",
        "root_service": "frontend",
        "deployment_names": [
            "frontend",
            "cartservice",
            "checkoutservice",
            "currencyservice",
            "emailservice",
            "paymentservice",
            "productcatalogservice",
            "recommendationservice",
            "shippingservice",
            "adservice",
        ],
    },
}

for app_cfg in APP_CONFIGS.values():
    app_cfg["host"] = f"http://{SERVER_IP}:{app_cfg['app_port']}"

APP = APP_CONFIGS[APP_NAME]
APP_PORT = APP["app_port"]
APP_HOST = APP["host"]

ONLINE_BOUTIQUE_HOST = APP_CONFIGS["onlineboutique"]["host"]
BOOKINFO_HOST = APP_CONFIGS["bookinfo"]["host"]

#WORKLOAD_NAME = ["stepped-400-up"]
#WORKLOAD_NAME = ["2026_world_cup", "wiki_load", "stepped-400-up" ]
WORKLOAD_NAME = ["wiki_load"]

#WORKLOAD_NAME = ["wiki_load","2026_world_cup"]


# "stepped-500-up"]


#WORKLOAD_NAME = ["constant-20"]

#WORKLOAD_NAME = ["linear-up-down-300"]
#WORKLOAD_NAME = ["linear-200"]
#WORKLOAD_NAME = ["linear-100", "linear-200", "linear-300", "linear-400", "linear-500"]
#WORKLOAD_NAME = ["low-high-100", "low-high-200", "low-high-300", "low-high-400", "low-high-500"]
#WORKLOAD_NAME = ["linear-200"]
#WORKLOAD_NAME = ["stepped-500-up"]
#, "wiki_load"]


LOCUST_FILES = {
    app_name: app_cfg["locust_file"]
    for app_name, app_cfg in APP_CONFIGS.items()
}

AUTOSCALER_SETTINGS = [

#    {
#         "autoscaler_name": "pbscaler",
#         "deployment_names": APP["deployment_names"],
#         "config": {
#             "image": "proactivellmbasedproject/pbscaler-boutique:latest",
#             "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090",
#             "kubeconfig_secret": "pbscaler-kubeconfig",

#             # PBScaler settings
#             "slo_ms": 500,
#             "num_services": len(APP["deployment_names"]),

#             # App metadata
#             "app_name": APP_NAME,
#             "root_service": APP["root_service"],
#         },
#   },


#     {
#         "autoscaler_name": "das",
#         "deployment_names": APP["deployment_names"],
#         "config": {
#             "image": "zewang42/das-autoscaler:latest",
#             "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#             "interval": 30,
#             "cooldown_seconds": 30,
#             "alpha_down_threshold": 30,
#             "tau_min": 60,
#             "tau_max": 80,
#             "beta_up_threshold": 95,
#             "min_replicas": 1,
#             "max_replicas": 20,
#         },
#     },
#          {
#         "autoscaler_name": "das",
#         "deployment_names": APP["deployment_names"],
#         "config": {
#             "image": "zewang42/das-autoscaler:latest",
#             "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#             "interval": 30,
#             "cooldown_seconds": 30,
#             "alpha_down_threshold": 30,
#             "tau_min": 60,
#             "tau_max": 80,
#             "beta_up_threshold": 95,
#             "min_replicas": 1,
#             "max_replicas": 20,
#         },
#     },




#{
#    "autoscaler_name": "default_cpu",
#    "deployment_names": APP["deployment_names"],
#    "config": {
#        "average_cpu_utilization": 80,
#        "min_replicas": 1,
#        "max_replicas": 20,
#
#        # Scale up behavior
#        "scale_up_stabilization_window_seconds": 0,
#        "scale_up_select_policy": "Max",
#        "scale_up_policy_type": "Percent",
#        "scale_up_policy_value": 100,
#        "scale_up_policy_period_seconds": 15,
#
#        # Scale down behavior
#        "scale_down_stabilization_window_seconds": 120,
#        "scale_down_select_policy": "Max",
#        "scale_down_policy_type": "Percent",
#        "scale_down_policy_value": 100,
#        "scale_down_policy_period_seconds": 15,
#    },
#},
#{
#    "autoscaler_name": "default_cpu",
#    "deployment_names": APP["deployment_names"],
#    "config": {
#        "average_cpu_utilization": 80,
#        "min_replicas": 1,
#        "max_replicas": 20,
#
#        # Scale up behavior
#        "scale_up_stabilization_window_seconds": 0,
#        "scale_up_select_policy": "Max",
#        "scale_up_policy_type": "Percent",
#        "scale_up_policy_value": 100,
#        "scale_up_policy_period_seconds": 15,
#
#        # Scale down behavior
#        "scale_down_stabilization_window_seconds": 300,
#        "scale_down_select_policy": "Max",
#        "scale_down_policy_type": "Percent",
#        "scale_down_policy_value": 100,
#        "scale_down_policy_period_seconds": 15,
#    },
#},
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },
#
#
#{
#    "autoscaler_name": "default_cpu",
#    "deployment_names": APP["deployment_names"],
#    "config": {
#        "average_cpu_utilization": 80,
#        "min_replicas": 1,
#        "max_replicas": 20,
#
#        # Scale up behavior
#        "scale_up_stabilization_window_seconds": 0,
#        "scale_up_select_policy": "Max",
#        "scale_up_policy_type": "Percent",
#        "scale_up_policy_value": 100,
#        "scale_up_policy_period_seconds": 15,
#
#        # Scale down behavior
#        "scale_down_stabilization_window_seconds": 120,
#        "scale_down_select_policy": "Max",
#        "scale_down_policy_type": "Percent",
#        "scale_down_policy_value": 100,
#        "scale_down_policy_period_seconds": 15,
#    },
#},
#{
#    "autoscaler_name": "default_cpu",
#    "deployment_names": APP["deployment_names"],
#    "config": {
#        "average_cpu_utilization": 80,
#        "min_replicas": 1,
#        "max_replicas": 20,
#
#        # Scale up behavior
#        "scale_up_stabilization_window_seconds": 0,
#        "scale_up_select_policy": "Max",
#        "scale_up_policy_type": "Percent",
#        "scale_up_policy_value": 100,
#        "scale_up_policy_period_seconds": 15,
#
#        # Scale down behavior
#        "scale_down_stabilization_window_seconds": 300,
#        "scale_down_select_policy": "Max",
#        "scale_down_policy_type": "Percent",
#        "scale_down_policy_value": 100,
#        "scale_down_policy_period_seconds": 15,
#    },
#},


# Ze-HERE


#        {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 120,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#                {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 300,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#
#        {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 120,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#                {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 300,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#
#        {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 120,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#                {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 300,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#
#        {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 120,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#                {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 300,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#
#        {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 120,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },
#                {
#            "autoscaler_name": "default_cpu",
#            "deployment_names": APP["deployment_names"],
#            "config": {
#                "average_cpu_utilization": 60,
#                "min_replicas": 1,
#                "max_replicas": 20,
#
#                # Scale up behavior
#                "scale_up_stabilization_window_seconds": 0,
#                "scale_up_select_policy": "Max",
#                "scale_up_policy_type": "Percent",
#                "scale_up_policy_value": 100,
#                "scale_up_policy_period_seconds": 15,
#
#                # Scale down behavior
#                "scale_down_stabilization_window_seconds": 300,
#                "scale_down_select_policy": "Max",
#                "scale_down_policy_type": "Percent",
#                "scale_down_policy_value": 100,
#                "scale_down_policy_period_seconds": 15,
#            },
#        },


#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#      
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#      
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#      
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#
#
#
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#
#
#
#
#
      {
          "autoscaler_name": "customdas-cpu-queue",
          "deployment_names": APP["deployment_names"],
          "config": {
              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
              "queue_model": "mmc",
              "latency_slo_mode": "adaptive",
              "slo_ms": 500,
              "slo_leaf_ms": 20,
              "slo_latency_percentile": "p95",
              "queue_model_percentile": "p95",
              "min_replicas": 1,
              "max_replicas": 20,
              "ggc_k_min": 0.7,
              "interval": 15,
              "cooldown_seconds": 120,
          },
      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },



#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#




#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.7,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },



#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.8,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.8,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.9,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0.9,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 1.0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 1.0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#      },
#
#




#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },

#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },
#
#
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 120,
#          },
#      },
#      {
#          "autoscaler_name": "customdas-cpu-queue",
#          "deployment_names": APP["deployment_names"],
#          "config": {
#              "image": "zewang42/customdas-autoscaler-cpu-queue:latest",
#              "prom_url": "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query",
#              "queue_model": "mmc",
#              "latency_slo_mode": "adaptive",
#              "slo_ms": 500,
#              "slo_leaf_ms": 20,
#              "slo_latency_percentile": "p95",
#              "queue_model_percentile": "p95",
#              "min_replicas": 1,
#              "max_replicas": 20,
#              "ggc_k_min": 0,
#              "interval": 15,
#              "cooldown_seconds": 300,
#          },
#        },
#


]


DURATION_SECONDS = 60 * 2
MONITOR_INTERVAL = 5
LATENCY_PERCENTILE = "p95"
PROM_URL = "http://prometheus.istio-system.svc.cluster.local:9090/api/v1/query"

TMP_DIR = "tmp"
WAIT_BETWEEN_EXPERIMENTS_SECONDS = 60

