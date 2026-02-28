#!/usr/bin/env bash

# 1. Environment Logic: Ensure K3s config is visible
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
NAMESPACE="default"
INTERVAL=5
PROM="http://localhost:9090/api/v1/query"

echo "=== Ambient Mesh Monitor (Broad Logic) ==="
echo "Monitoring $NAMESPACE namespace via Prometheus at $PROM"
echo "Capturing Gateway (Source) and Waypoint (Destination) metrics."
echo ""

# Helper to handle nulls/NaNs from Prometheus JSON
round1() {
  if [[ -z "$1" || "$1" == "null" || "$1" == "NaN" || "$1" == "0" ]]; then
     printf "0.0"
  else
     printf "%.1f" "$1"
  fi
}

while true; do
  echo "[$(date '+%T')] Mapping Mesh Traffic..."
  echo "SERVICE              HTTP_RPM  HTTP_LAT   gRPC_RPM  gRPC_LAT   CPU(ms) MEM(MiB) PODS"
  echo "--------------------------------------------------------------------------------------"

  # Get list of services from deployments
  services=$(kubectl get deploy -n "$NAMESPACE" --no-headers | awk '{print $1}')

  for svc in $services; do

    # 2. HTTP Logic: Broad filter catches the 80k+ Gateway requests (reporter=source)
    http_rpm=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_requests_total{request_protocol=\"http\", destination_workload=\"$svc\"}[2m])) * 60" \
      2>/dev/null | jq -r '.data.result[0].value[1]')

    http_lat=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{request_protocol=\"http\", destination_workload=\"$svc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{request_protocol=\"http\", destination_workload=\"$svc\"}[2m]))" \
      2>/dev/null | jq -r '.data.result[0].value[1]')

    # 3. gRPC Logic: Captures internal pod-to-pod backend traffic
    grpc_rpm=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_requests_total{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m])) * 60" \
      2>/dev/null | jq -r '.data.result[0].value[1]')

    grpc_lat=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{request_protocol=\"grpc\", destination_workload=\"$svc\"}[2m]))" \
      2>/dev/null | jq -r '.data.result[0].value[1]')

    # 4. System Logic: Pod Resources
    cpu_raw=$(kubectl top pod -n "$NAMESPACE" 2>/dev/null | grep "$svc" | awk '{gsub("m","",$2); sum+=$2} END {print sum+0}')
    cpu=$cpu_raw
    #cpu=$(echo "scale=2; $cpu_raw/1000" | bc)
    mem_raw=$(kubectl top pod -n "$NAMESPACE" 2>/dev/null | grep "$svc" | awk '{gsub("Mi","",$3); sum+=$3} END {print sum+0}')
    pods=$(kubectl get pod -n "$NAMESPACE" --no-headers 2>/dev/null | grep "$svc" | grep "Running" | wc -l)

    printf "%-20s %-9s %-10s %-9s %-10s %-9s %-8s %-5s\n" \
      "$svc" \
      "$(round1 "$http_rpm")" \
      "$(round1 "$http_lat")" \
      "$(round1 "$grpc_rpm")" \
      "$(round1 "$grpc_lat")" \
      "$cpu" \
      "$mem_raw" \
      "$pods"
  done
  echo ""
  sleep $INTERVAL
done

