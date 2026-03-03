class Config:
    def __init__(self):
        self.select_benchmark = 'book-info'
        #self.select_benchmark = 'online-boutique'
        self.select_scaler = 'KHPA-80' # [None, KHPA-20, KHPA-50, KHPA-80, Showar, PBScaler]
        self.locust_exp_name = 'wiki'
        self.locust_exp_time = 6
        self.locust_load_dist = '1'

        # Prometheus config
        self.prom_url=f'http://192.168.31.130:30001'

        # Kubernetes config
        self.kube_config = './config/kube.yaml'

        # benchmark config
        self.benchmarks = {
            'online-boutique': {
                'entry': 'http://3.8.148.228:8080/', # check the port of istio-ingress-gateway
                'deploy_path': './benchmarks/online-boutique/online-boutique.yaml',
                'istio_yaml': './benchmarks/online-boutique/istio-manifests.yaml',
                'namespace': 'online-boutique',
                'SLA': 500
            },
            'book-info': {
                'entry': 'http://13.135.128.217:8080/', # check the port of istio-ingress-gateway
                'SLA': 500
            }
        }
