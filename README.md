# Swarmchestrate-Decentralised-Auto-Scaling
The repo documents the neccessary materials and steps to launch, stress, and monitor an e-commerce applciation, i.e., online-boutique.
Then one could perform monitoring to record the training data for the autoscaler. 
One could also deploy k3s default HPA to test the performance of app.

# Setup

## 1. VM cluster creation
Create a cluster of VM. 
Requirements:

Memory > 2GB

Allow all TCP traffic

Allow all UDP traffic

Clone this repostory to the master VM
Github key should be copied first
```sh
git clone git@github.com:ZeWang42/Swarmchestrate-Decentralised-Auto-Scaling.git
```
---

## 2. k3s cluster creation

Set up a k3s cluster to host application.

Follow the instructions in /k3s-installation

---

## 3. Install Istio Monitor

Set up istio service mesh in amibent mode to collect metrics, note that sidecar mode is abandoned due to high resource overhead.

Follow the instructions in /istio-installation

---

## 4. Deploy application

Deploy application and monitor its runtime metrics.

Follow the instructions in /application folder


---

## 5. Generate loads

Install and config locust to generate loads and stress the deployed application.

Follow the instructions in /load-generation

## Contact

Have a smooth setup process and have fun. 

Feel free to enquire and report any issues to:

Ze Wang - email: z.wang3@napier.ac.uk



