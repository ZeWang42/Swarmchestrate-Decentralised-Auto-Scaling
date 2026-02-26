# This folder documents how to create a k3s cluster

## Step 1: install master node
Edit private ip of master-config
```sh
vim master-config.json
```
---
Run installation script
```sh
./1-install-master.sh
```
---
## Step 2: retrieve token and bypass sudo control
```sh
./2-master-fetch-token.sh
``` 
---
## Step 3: install worker
Edit private ip and token in worker-config.json
```sh
vim worker-config.json
``` 
Run worker installation script
```sh
./3-install-worker.sh
``` 
