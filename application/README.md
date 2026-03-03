This folder contains:

/yaml : k3s manifests of online boutique application

/sh : scripts to deploy application and perform monitoring

/py : utilities to extract monitored data

After successfully deployed istio on a k3s cluster, one should follow the steps below to deploy the application and perform monitoring

## Step 1: deploy application and frontend gateway

Note that a gateway must be created for driving traffic through waypoints so that istio could monitor http requests
```sh
sudo kubectl delete -f ../yaml/online-boutique.yaml
sudo kubectl delete -f ../yaml/hpa-online-boutique.yaml
sudo kubectl apply -f ../yaml/online-boutique.yaml
sudo kubectl apply -f ../yaml/frontend-gateway.yaml
sudo kubectl port-forward -n default svc/frontend-gateway-istio 8080:80 --address 0.0.0.0 &
```

## Step 2: export prometheus

Export prometheus using nodeport so that monitoring scripts could scrape metrics
```sh
kubectl port-forward svc/prometheus -n istio-system 9090:9090
```

## Step 3: monitor

Run scripts to monitor: 

1) http requests/latency
2) grpc requests/latency
3) CPU usage in ms
4) Mem usage in MiB
5) #replicas
   
Http requests only enter frontend gateway and the frontend microservice communicates to the others through grpc call.

```sh
./3-monitor-ambient-mesh.sh
```


