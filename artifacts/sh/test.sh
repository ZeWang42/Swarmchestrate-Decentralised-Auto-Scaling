#!/usr/bin/env bash

NAMESPACE="default"
INTERVAL=6
PROM="http://localhost:9090/api/v1/query"

round1() { 
  if [[ -z "$1" || "$1" == "null" || "$1" == "NaN" ]]; then 
     printf "0.00"
  else
     printf "%.2f" "$1"
  fi
}

while true; do
  echo "[$(date '+%F %T')]"
  echo "SERVICE              HTTP_RPM  HTTP_LAT   gRPC_RPM  gRPC_LAT   CPU_CR  MEM(MiB) PODS CPU_RATIO"
  echo "--------------------------------------------------------------------------------------------"

  services=$(kubectl get deploy -n "$NAMESPACE" --no-headers | awk '{print $1}')

  for svc in $services; do

    # HTTP RPM
    http_rpm=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_requests_total{reporter=\"destination\", request_protocol=\"http\", destination_service_name=\"$svc\"}[1m]))" \
      | jq -r '.data.result[0].value[1]')

    # HTTP Latency
    http_lat=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{reporter=\"destination\", request_protocol=\"http\", destination_service_name=\"$svc\"}[1m]))
       / sum(rate(istio_request_duration_milliseconds_count{reporter=\"destination\", request_protocol=\"http\", destination_service_name=\"$svc\"}[1m]))" \
      | jq -r '.data.result[0].value[1]')

    # gRPC RPM
    grpc_rpm=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_requests_total{reporter=\"destination\", request_protocol=\"grpc\", destination_service_name=\"$svc\"}[1m]))" \
      | jq -r '.data.result[0].value[1]')

    # gRPC Latency
    grpc_lat=$(curl -sG "$PROM" \
      --data-urlencode "query=sum(rate(istio_request_duration_milliseconds_sum{reporter=\"destination\", request_protocol=\"grpc\", destination_service_name=\"$svc\"}[1m]))
       / sum(rate(istio_request_duration_milliseconds_count{reporter=\"destination\", request_protocol=\"grpc\", destination_service_name=\"$svc\"}[1m]))" \
      | jq -r '.data.result[0].value[1]')

    # CPU in cores
    cpu_raw=$(kubectl top pod -n "$NAMESPACE" | grep "$svc" | awk '{gsub("m","",$2); sum+=$2} END {print sum+0}')
    cpu=$(echo "scale=2; $cpu_raw/1000" | bc)

    # Memory
    mem_raw=$(kubectl top pod -n "$NAMESPACE" | grep "$svc" | awk '{gsub("Mi","",$3); sum+=$3} END {print sum+0}')

    # Pod count
    pods=$(kubectl get pod -n "$NAMESPACE" | grep "$svc" | wc -l)

    #### CPU_RATIO FIXED ####
    cpu_ratio=$(curl -sG "$PROM" \
      --data-urlencode "query=max(sum(irate(container_cpu_usage_seconds_total{namespace=\"default\", pod=~\"$svc.*\", container!=\"POD\"}[5m])) by (pod)) / max(sum(kube_pod_container_resource_requests_cpu_cores{namespace=\"default\", pod=~\"$svc.*\"}) by (pod))" \
      | jq -r '.data.result[0].value[1]')

    printf "%-20s %-9s %-10s %-9s %-10s %-6s %-8s %-4s %-9s\n" \
      "$svc" \
      "$(round1 "$http_rpm")" \
      "$(round1 "$http_lat")" \
      "$(round1 "$grpc_rpm")" \
      "$(round1 "$grpc_lat")" \
      "$cpu" \
      "$mem_raw" \
      "$pods" \
      "$(round1 "$cpu_ratio")"

  done

  echo ""
  sleep $INTERVAL
done

