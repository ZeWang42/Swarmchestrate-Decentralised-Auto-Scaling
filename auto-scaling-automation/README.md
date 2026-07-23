# 🚀 Autoscaling Experiment Automation Tool

This project provides an automated framework to run **reproducible autoscaling experiments** on Kubernetes using a **client–server architecture**.

## 📌 Features

- 📚 Bookinfo support  
- 🛒 Online Boutique support  
- ⚙️ Multiple autoscalers (CPU HPA, DAS, CustomDAS)  
- 📊 Prometheus-based monitoring  
- 🔥 Realistic workload generation via Locust  

---

## 🧠 Motivation

Autoscaling experiments are typically hard to reproduce because they require:

- Deploying applications  
- Configuring gateways and networking  
- Installing monitoring (Prometheus)  
- Injecting autoscaler configurations  
- Generating workloads  
- Collecting metrics  

This tool automates the entire pipeline, enabling:

- ✅ Fair comparison across autoscalers  
- ✅ Consistent experiment setup  
- ✅ Reproducibility  

---

## 🏗️ Architecture

Client (Locust + Orchestrator)  
        ↓  
Autoscaler Server (FastAPI)  
        ↓  
Kubernetes Cluster  

---

## ⚙️ Features

### 🧑‍💻 Client
- Define experiment matrix (apps × workloads × autoscalers)
- Send setup/cleanup requests to server
- Run Locust load tests (CSV-driven)
- Collect performance metrics
- Store experiment results automatically

### 🖥️ Server (Kubernetes Deployment)

Responsible for:

- Environment setup (Istio, Gateway API, Prometheus)
- Application lifecycle (Bookinfo & Online Boutique)
- Autoscaler management (CPU HPA, DAS, CustomDAS)
- Monitoring (Prometheus metrics)

---

## 📦 Supported Applications

### 📚 Bookinfo
- productpage
- reviews
- ratings
- details

### 🛒 Online Boutique
- frontend
- checkoutservice
- cartservice
- productcatalogservice

---

## 📁 Project Structure

server/  
client/  
tmp/  

---

## 🚀 Quick Start

### Deploy Server

kubectl apply -f server/server-manifest.yaml

### Expose Server (NodePort)

kubectl patch svc autoscaler-server -p '{"spec":{"type":"NodePort"}}'

### Run Client

pip install -r client/requirements.txt  
python load.py  

---

## 📊 Output

tmp/experiment_summary.csv  
tmp/locust/  

---

## ⚠️ Notes

- CPU autoscaling requires resource requests  
- Uses Kubernetes Gateway API  
- Open NodePort in cloud firewall  

---

## 🧠 Summary

- Reproducible experiments  
- Automated setup  
- Multi-app support  
- Realistic workloads  
