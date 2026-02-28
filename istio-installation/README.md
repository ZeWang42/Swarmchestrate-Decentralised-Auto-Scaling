# Istio installation

The following steps will install Istio in ambient mode. For a quick setup, one can install istio by running through all 6 scripts one by one.

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

expose gateway to internet
```sh
sudo kubectl port-forward -n default svc/frontend-gateway-istio 8080:80 --address 0.0.0.0 &
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
kubectl -n default annotate svc waypoint \
  prometheus.io/scrape="true" \
  prometheus.io/port="15020" \
  prometheus.io/path="/stats/prometheus"
```

open prometheus listener

```sh
kubectl -n istio-system port-forward svc/prometheus 9090:9090
```

run this on master node, it maps prometheus pod to ec2's localhost
```sh
istioctl dashboard prometheus --address 0.0.0.0
```

On local laptop create a tunnel to connect laptop to the ec2 instance
```sh
ssh -i your-key.pem -L 9090:localhost:9090 ec2-user@<EC2-PUBLIC-IP>
```

## (optional) Step 7: kiali

Kiali enables you to visualise traffic flow diagram among microservices.

Install Kiali
```sh
kubectl apply -f ${ISTIO_HOME}/samples/addons/kiali.yaml
```

Expose for Remote Access:
```sh
istioctl dashboard kiali --address 0.0.0.0
```

On your Local Laptop, open a new terminal to bridge the EC2 port to your browser:
```sh
ssh -i your-key.pem -L 20001:localhost:20001 ec2-user@<YOUR-EC2-IP>
```

## Pitfalls

Locust via NodePort: If Locust is hitting http://<Node-IP>:31444, the traffic goes: Locust -> NodePort -> Frontend Pod. It completely bypasses the Waypoint because NodePorts connect directly to the pod's network. This prevents waypoint to monitor http requests.
