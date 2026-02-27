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
TCP ports 
UDP ports

Follow the instructions in /k3s-installation


### 2. Clone this repostory to the master VM
Github key should be copied first
```sh
git clone git@github.com:ZeWang42/Swarmchestrate-Decentralised-Auto-Scaling.git
```

### 3. Deploy application
```sh
cd ./Swarmchestrate-Decentralised-Auto-Scaling/artifacts/sh
./restartOnline-boutique.sh
```

### 4. Monitor
Follow the instructions in /monitor
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

### 5. Generate loads
TODO: this should be on a separate machine, should add a new folder for locust and how to use it, then just follow the instructions on there 
Follow the instructions in /load-generation
```sh
```




