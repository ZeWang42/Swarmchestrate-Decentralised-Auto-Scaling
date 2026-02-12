# Swarmchestrate-Decentralised-Auto-Scaling
The repo documents the materials to launch online-boutique application on an existing k3s cluster.
Then one could perform monitoring to record the training data for the autoscaler. 
One could also deploy HPA to test the performance of app.

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
TODO
```sh
```

### 4. Deploy application
TODO
```sh
cd ./Swarmchestrate-Decentralised-Auto-Scaling/artifacts/sh
./restartOnline-boutique.sh
```

### 5. Generate loads
TODO
```sh
```

### 6. Monitor
TODO
```sh
```


