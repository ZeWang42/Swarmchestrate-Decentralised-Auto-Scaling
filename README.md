# Swarmchestrate-Decentralised-Auto-Scaling
The repo documents the materials to launch online-boutique application on an existing k3s cluster.
Then one could perform monitoring to record the training data for the autoscaler. 
One could also deploy k3s default HPA to test the performance of app.

## Setup

### 1. k3s cluster creation
Create a cluster of VM. 
Create a k3s cluster.
Requirements:
Memory > 2GB

Follow the instructions in /k3s-installation


### . Clone this repostory to the master VM
Github key should be copied first
```sh
git clone git@github.com:ZeWang42/Swarmchestrate-Decentralised-Auto-Scaling.git
```

### 4. Deploy application
```sh
cd ./Swarmchestrate-Decentralised-Auto-Scaling/artifacts/sh
./restartOnline-boutique.sh
```

### 5. Generate loads
TODO: this should be on a separate machine, should add a new folder for locust and how to use it, then just follow the instructions on there 

```sh
```

### 6. Monitor
Set prometheus server, istio amibent mode, run monitor script
Dowload Istio

```sh
curl -L https://istio.io/downloadIstio | sh -
```

Install Istio with ambient mode, not using sidecar since it introduces severe CPU overhead
```sh
sudo $PWD/istio-1.29.0/bin/istioctl install \
  --kubeconfig /etc/rancher/k3s/k3s.yaml \
  --set profile=ambient \
  --set values.global.platform=k3s \
  --set values.cni.cniConfDir=/var/lib/rancher/k3s/agent/etc/cni/net.d \
  --set values.cni.cniBinDir=/var/lib/rancher/k3s/data/current/bin \
  -y
```

## K3s scripts

### Master node creation

Be careful with creating a k3s master master, do not use external ip but to use private ip otherwise worker node will points to wrong server api.

```sh
curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="server --node-ip <private_ip> --advertise-address <private_ip>" sh -
```

Fetch token
```sh
sudo cat /var/lib/rancher/k3s/server/node-token
```

### Worker node joining
```sh
curl -sfL https://get.k3s.io | K3S_URL="https://<ip_addr>:6443" K3S_TOKEN="<TOKEN>" sh -
```

### Worker node k3s agent deletion
```sh
sudo /usr/local/bin/k3s-agent-uninstall.sh
```


