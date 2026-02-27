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


