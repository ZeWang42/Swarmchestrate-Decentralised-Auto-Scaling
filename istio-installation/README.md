# Istio installation

## Step 1: download Istio

```sh
curl -L https://istio.io/downloadIstio | sh -
cd istio-1.29.0
export PATH=$PWD/bin:$PATH
```

## Step 2: install Istio k3s specific version with ambient profile

```sh
istioctl --kubeconfig /etc/rancher/k3s/k3s.yaml install --set profile=ambient --set values.global.platform=k3s
```

## Step 3: install/upgrade kubernetes gateway API CRDs

```sh
kubectl get crd gateways.gateway.networking.k8s.io &> /dev/null || \
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/experimental-install.yaml
```

## Step 4: add default namespace to the mesh

```sh
kubectl label namespace default istio.io/dataplane-mode=ambient
```

## Step 5: install prometheus

install prometheus and enable metrics scraping
```sh
kubectl apply -f samples/addons/prometheus.yaml
kubectl -n istio-system annotate svc ztunnel-metrics \
  prometheus.io/scrape="true" \
  prometheus.io/port="15020" \
  prometheus.io/path="/metrics" --overwrite
```


open prometheus listener

```sh
kubectl -n istio-system port-forward svc/prometheus 9090:9090
```

