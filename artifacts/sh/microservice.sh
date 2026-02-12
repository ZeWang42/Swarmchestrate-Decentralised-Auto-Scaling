#!/usr/bin/env bash

NAMESPACE="default"
PROM="http://localhost:9090/api/v1/query"
INTERVAL=4

echo "=== Monitoring microservice metrics (Frontend HTTP + CPU/MEM without Gateway) ==="
echo "Press Ctrl+C to stop."
echo ""

round2() {
  if [[ -z "$1" || "$1" == "null" || "$1" == "NaN" ]]; then
    printf "0.00"
  else
    printf "%.2f" "$1"
  fi
}

while true; do
  echo "[$(date '+%F %T')]"
  printf "%-26s %-10s %-15s %-14s %-14s %-5s\n" \
    "SERVICE" "HTTP_RPS" "HTTP_LAT(ms)" "CPU_UTIL(%)" "MEM_UTIL(%)" "PODS"
  echo "--------------------------------------------------------------------------------------"

  services=$(kubectl get deploy -n "$NAMESPACE" --no-headers | awk '{print $1}')

  for svc in $services; do
    # Skip gateway-related workloads
    if [[ "$svc" == *"gateway"* ]]; then
      continue
    fi

    # Count pods
    pods=$(kubectl get pods -n "$NAMESPACE" -l app=$svc --no-headers 2>/dev/null | wc -l)
    [[ "$pods" -eq 0 ]] && continue

    # ===============================
    # FRONTEND HTTP METRICS
    # ===============================
    if [[ "$svc" == "frontend" ]]; then
      http_rps=$(curl -sG "$PROM" \
        --data-urlencode 'query=sum(rate(istio_requests_total{destination_service_name="frontend"}[1m]))' \
        | jq -r '.data.result[0].value[1]')
      http_lat=$(curl -sG "$PROM" \
        --data-urlencode 'query=sum(rate(istio_request_duration_milliseconds_sum{destination_service_name="frontend"}[1m])) 
         / sum(rate(istio_request_duration_milliseconds_count{destination_service_name="frontend"}[1m]))' \
        | jq -r '.data.result[0].value[1]')
    else
      http_rps="0"
      http_lat="0"
    fi

    # ===============================
    # CPU UTILIZATION (%)
    # ===============================
    # Get total CPU usage (millicores)
    cpu_used=$(kubectl top pod -n "$NAMESPACE" --no-headers \
      | awk -v svc="^${svc}-" '$1 ~ svc && $1 !~ /gateway/ {
          v=$2;
          if(v ~ /m$/) cpu += substr(v, 1, length(v)-1);
          else cpu += v * 1000;
        }
        END { print cpu }')

    # Get per-pod CPU limit from deployment
    cpu_limit=$(kubectl get deploy "$svc" -n "$NAMESPACE" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null)

    if [[ -z "$cpu_limit" ]]; then
      cpu_limit="200m"  # default fallback if not defined
    fi

    if [[ "$cpu_limit" == *"m" ]]; then
      cpu_limit=${cpu_limit%m}
    else
      cpu_limit=$(echo "$cpu_limit * 1000" | bc)
    fi

    cpu_limit_total=$(echo "$cpu_limit * $pods" | bc -l)
    cpu_util="0"
    if (( $(echo "$cpu_limit_total > 0" | bc -l) )); then
      cpu_util=$(echo "scale=2; ($cpu_used / $cpu_limit_total) * 100" | bc -l)
    fi

    # ===============================
    # MEMORY UTILIZATION (%)
    # ===============================
    mem_used=$(kubectl top pod -n "$NAMESPACE" --no-headers \
      | awk -v svc="^${svc}-" '$1 ~ svc && $1 !~ /gateway/ {
          v=$3;
          if(v ~ /Mi$/) mem += substr(v, 1, length(v)-2);
          else if(v ~ /Gi$/) mem += substr(v, 1, length(v)-2) * 1024;
        }
        END { print mem }')

    mem_limit=$(kubectl get deploy "$svc" -n "$NAMESPACE" \
      -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null)

    if [[ -z "$mem_limit" ]]; then
      mem_limit="256Mi"
    fi

    if [[ "$mem_limit" == *"Mi" ]]; then
      mem_limit=${mem_limit%Mi}
    elif [[ "$mem_limit" == *"Gi" ]]; then
      mem_limit=$(echo "${mem_limit%Gi} * 1024" | bc)
    fi

    mem_limit_total=$(echo "$mem_limit * $pods" | bc -l)
    mem_util="0"
    if (( $(echo "$mem_limit_total > 0" | bc -l) )); then
      mem_util=$(echo "scale=2; ($mem_used / $mem_limit_total) * 100" | bc -l)
    fi

    # ===============================
    # OUTPUT
    # ===============================
    printf "%-26s %-10s %-15s %-14s %-14s %-5s\n" \
      "$svc" \
      "$(round2 "$http_rps")" \
      "$(round2 "$http_lat")" \
      "$(round2 "$cpu_util")" \
      "$(round2 "$mem_util")" \
      "$pods"
  done

  echo ""
  sleep "$INTERVAL"
done

