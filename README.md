# Swarmchestrate-Decentralised-Auto-Scaling
The repo documents the materials to launch online-boutique application on an existing k3s cluster.
Then one could perform monitoring to record the training data for the autoscaler. 
One could also deploy HPA to test the performance of app.

## Environment Setup
Create a cluster of VM using Swarmchestrate platform.
Enters the master node.

##
Bypass sudo control
```sh
sudo chown $USER:$USER /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
```
