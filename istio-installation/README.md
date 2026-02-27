# Istio installation

## Step 1: download Istio

```sh
curl -L https://istio.io/downloadIstio | sh -
cd istio-1.29.0
export PATH=$PWD/bin:$PATH
```
ensure istio env correctly located

```sh
mkdir -p ~/.kube
sudo cp /etc/rancher/k3s/k3s.yaml ~/.kube/config
sudo chown $(whoami):$(whoami) ~/.kube/config
export KUBECONFIG=~/.kube/config
```

---

## Step 2: install Istio k3s specific version with ambient profile

```sh
istioctl install --set profile=ambient --set values.global.platform=k3s
```

---

## Step 3: install/upgrade kubernetes gateway API CRDs

```sh
kubectl get crd gateways.gateway.networking.k8s.io &> /dev/null || \
kubectl apply --server-side -f https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.4.0/experimental-install.yaml
```

---

## Step 4: add default namespace to the mesh

```sh
kubectl label namespace default istio.io/dataplane-mode=ambient
```

---

## Step 5: add waypoint to monitor Layer 7 metrics

```sh
istioctl waypoint apply -n default --enroll-namespace
```
Label the ns for waypoint use to ensure services know to route through the proxy

```sh
kubectl label namespace default istio.io/use-waypoint=waypoint
```

If pods were running before the labels were applied, restart them to ensure they have the correct mTLS certificates.

```sh
kubectl port-forward -n default pod/<waypoint-pod-name> 15020:15020
curl -s localhost:15020/stats/prometheus | grep istio_requests_total
```

---

## Step 6: install prometheus

install prometheus and enable metrics scraping
```sh
kubectl apply -f samples/addons/prometheus.yaml
kubectl -n istio-system annotate svc ztunnel-metrics \
  prometheus.io/scrape="true" \
  prometheus.io/port="15020" \
  prometheus.io/path="/metrics" --overwrite
```

```sh
kubectl apply -f samples/addons/prometheus.yaml
kubectl -n default annotate svc waypoint \
  prometheus.io/scrape="true" \
  prometheus.io/port="15020" \
  prometheus.io/path="/stats/prometheus"
```

open prometheus listener

```sh
kubectl -n istio-system port-forward svc/prometheus 9090:9090
```

