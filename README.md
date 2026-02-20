# Swarmchestrate-Decentralised-Auto-Scaling
The repo documents the materials to launch online-boutique application on an existing k3s cluster.
Then one could perform monitoring to record the training data for the autoscaler. 
One could also deploy k3s default HPA to test the performance of app.

## Setup

### 1. Create cluster
Create a cluster of VM using Swarmchestrate platform.
Enters the master node.

### 2. Release sudo control
Bypass sudo control
```sh
sudo chown $USER:$USER /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```

### 3. Clone this repostory to the master VM
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
TODO: this should be on a separate machine
```sh
```

### 6. Monitor
TODO
```sh
```

## K3s scripts

### Worker node joining
```sh
curl -sfL https://get.k3s.io | K3S_URL="https://<ip_addr>:6443" K3S_TOKEN="<TOKEN>" sh -
```

### Worker node k3s agent deletion
```sh
sudo /usr/local/bin/k3s-agent-uninstall.sh
```

### Pitfalls

Be careful with creating k3s master, do not use external ip but to use private ip otherwise worker node will points to wrong server api.
