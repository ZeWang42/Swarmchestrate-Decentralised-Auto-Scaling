#!/usr/bin/env bash

# 1. Configuration
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
NAMESPACE="default"
INTERVAL=5
PROM="http://localhost:9090/api/v1/query"
LOG_FILE="mesh_metrics_$(date +%Y%m%d_%H%M%S).csv"

echo "=== Ambient Mesh Monitor ==="
echo "Logging to: $LOG_FILE"
echo "Press [CTRL+C] to stop."
echo ""

# Write CSV Header
echo "Timestamp,Service,HTTP_RPM,HTTP_LAT,gRPC_RPM,gRPC_LAT,CPU_ms,MEM_MiB,Pods" > "$LOG_FILE"

# Helper to handle nulls/NaNs and format numbers
round1() {
  if [[ -z "$1" || "$1" == "null" || "$1" == "NaN" || "$1" == "0" ]]; then
     echo "0.0"
  else
     printf "%.1f" "$1"
  fi
}

while true; do
  # Fetch list of service workloads in the namespace
  services=$(kubectl get deploy -n "$NAMESPACE" -o jsonpath='{.items[*].metadata.name}')
  
  # Terminal Header
  echo "[$(date '+%T')] Monitoring $NAMESPACE..."
  printf "%-20s %-9s %-10s %-9s %-10s %-9s %-8s %-5s\n" \
    "SERVICE" "H_RPM" "H_LAT" "G_RPM" "G_LAT" "CPU(ms)" "MEM(MiB)" "PODS"
  echo "--------------------------------------------------------------------------------------"

  for svc in $services; do

    # 2. HTTP Logic (Istio Source Metrics)
    http_rpm=$(curl -sG "$PROM" --data-urlencode "query=sum(rate(istio_requests_total{request_protocol=\"http\", destination_workload=\"$svc\"}[2m])) * 60" 2>/dev/null | jq -r '.data.result[0].value[1]')

    http_lat=$(curl -sG "$PROM" --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{request_protocol=\"http\", destination_workload=\"$svc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{request_protocol=\"http\", destination_workload=\"$svc\"}[2m]))" 2>/dev/null | jq -r '.data.result[0].value[1]')

    # 3. gRPC Logic (Istio Destination Metrics)
    grpc_rpm=$(curl -sG "$PROM" --data-urlencode "query=sum(rate(istio_requests_total{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m])) * 60" 2>/dev/null | jq -r '.data.result[0].value[1]')

    grpc_lat=$(curl -sG "$PROM" --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m]))" 2>/dev/null | jq -r '.data.result[0].value[1]')

    # 4. System Logic: Pod Resources (CPU in ms, Memory in MiB)
    cpu=$(kubectl top pod -n "$NAMESPACE" --no-headers 2>/dev/null | grep "$svc" | awk '{gsub("m","",$2); sum+=$2} END {print sum+0}')
    mem=$(kubectl top pod -n "$NAMESPACE" --no-headers 2>/dev/null | grep "$svc" | awk '{gsub("Mi","",$3); sum+=$3} END {print sum+0}')
    pods=$(kubectl get pod -n "$NAMESPACE" --no-headers 2>/dev/null | grep "$svc" | grep "Running" | wc -l)

    # Clean the numbers
    h_rpm=$(round1 "$http_rpm")
    h_lat=$(round1 "$http_lat")
    g_rpm=$(round1 "$grpc_rpm")
    g_lat=$(round1 "$grpc_lat")

    # 5. Output to Terminal
    printf "%-20s %-9s %-10s %-9s %-10s %-9s %-8s %-5s\n" \
      "$svc" "$h_rpm" "$h_lat" "$g_rpm" "$g_lat" "$cpu" "$mem" "$pods"

    # 6. Store in Log File (CSV)
    echo "$(date '+%Y-%m-%d %H:%M:%S'),$svc,$h_rpm,$h_lat,$g_rpm,$g_lat,$cpu,$mem,$pods" >> "$LOG_FILE"
  done

  echo ""
  sleep $INTERVAL
done

