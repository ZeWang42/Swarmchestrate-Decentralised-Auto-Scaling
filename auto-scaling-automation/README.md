# Autoscaling Experiment Automation Tool

This is an automation tool that enables hassle-free autoscaling experiments by eliminating the need for manual configuration. Additionally, it supports custom HPA integration.

The motivation behind this tool is that performing autoscaling experiments typically requires time-consuming manual effort to set up and configure the experimental testbed. This includes tasks such as deploying applications, setting up monitoring, injecting HPA configurations, and generating workloads.

The complexity and effort involved make it difficult to conduct fair and consistent comparative evaluations across different autoscaling strategies and scenarios (i.e., various combinations of applications, workloads, and HPAs). As a result, much of the existing work has been tested only in simulation environments or private setups, which lack reproducibility.

To this end, we introduce this tool, which adopts a client–server model. The client sends configuration requests to the server. After the server prepares the environment, the client generates workloads to stress the application.

---

# Features

The server is a container deployed as a Kubernetes Deployment in the testbed cluster. It is responsible for all preparation and configuration.

## Client
1. Query existing setups (HPA, applications)
2. Send requests (HPA, application)
3. Generate workloads to stress the application
4. Collect application-level QoS metrics

## Server
1. Prepare base environment:  
    a. Install and deploy Istio (Ambient mode; sidecar mode has high resource consumption)  
    b. Install gateway  
    c. Deploy Prometheus  
    d. Expose ports  
2. Deploy HPA and application  
3. Collect microservice- and HPA-level QoS performance metrics  

---

# Bookinfo Experiment Setup

This bundle contains:

- `server/server.py`: FastAPI autoscaling experiment server  
- `client/load.py`: client-side experiment orchestrator  
- `client/config/exp_config.py`: experiment matrix and endpoints  
- `client/load/book-info/wiki_locustfile.py`: Locust file using CSV-driven workload  
- `server/requirements.txt`  
- `client/requirements.txt`  

## Server run
```bash
pip install -r server/requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8080
```
## Client run
```bash
pip install -r requirements.txt
python load.py
```

## Notes

Update SERVER_BASE_URL and BOOKINFO_HOST in client/config/exp_config.py.
The client expects workload files:
load/book-info/workloads/constant-100.csv
load/book-info/workloads/constant-300.csv
load/book-info/workloads/constant-500.csv
load/book-info/workloads/wiki-workload.csv
The Locust file reads the workload path from the CSV_PATH environment variable.
