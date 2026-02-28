This folder contains:
/yaml : k3s manifests of online boutique application
/sh : scripts to deploy application and perform monitoring
/py : utilities to extract monitored data

After successfully deployed istio on a k3s cluster, one should follow the steps below to deploy application and perform monitoring

## Step 1: deploy application and frontend gateway

Note that a gateway must be created for driving traffic through waypoints so that istio could monitor http requests
```sh
cd ./sh
./1-restart-online-boutique.sh
```

## Step 2: export prometheus

Export prometheus using nodeport so that monitoring scripts could scrape metrics
```sh
./2-export-prometheus.sh
```

## Step 3: monitor

Run scripts to monitor: http requests/latency, grpc requests/latency, CPU usage in ms, Mem usage in MiB, number of replica of microservices.
Http requests only enter frontend gateway and the frontend microservice communicates to the others through grpc call.

```sh
./3-monitor-ambient-mesh.sh
```
