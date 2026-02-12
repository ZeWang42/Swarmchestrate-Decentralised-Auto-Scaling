#!/usr/bin/env bash

NAMESPACE="default"
INTERVAL=6
PROM="http://localhost:9090/api/v1/query"

echo "=== Monitoring per-pod metrics (HTTP + gRPC + Threads + CPU/MEM) ==="
echo "Press Ctrl+C to stop."
echo ""

round1() { printf "%.1f" "${1:-0}"; }

while true; do
  echo "[$(date '+%F %T')]"
  echo "POD                                      IP              NODE            HTTP_RPM HTTP_LAT RPC_IN  LAT_IN  RPC_OUT LAT_OUT CPU/MEM      THREADS"
  echo "---------------------------------------------------------------------------------------------------------------------------------------------------"

  # ---- PROMQL QUERIES ----

  http_rpm=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_requests_total{request_protocol="http", reporter="destination"}[1m]))')

  http_lat=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_request_duration_milliseconds_sum{request_protocol="http", reporter="destination"}[1m])) / sum by (pod) (rate(istio_request_duration_milliseconds_count{request_protocol="http", reporter="destination"}[1m]))')

  grpc_in_rpm=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_requests_total{request_protocol="grpc", reporter="destination"}[1m]))')

  grpc_in_lat=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_request_duration_milliseconds_sum{request_protocol="grpc", reporter="destination"}[1m])) / sum by (pod) (rate(istio_request_duration_milliseconds_count{request_protocol="grpc", reporter="destination"}[1m]))')

  grpc_out_rpm=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_requests_total{request_protocol="grpc", reporter="source"}[1m]))')

  grpc_out_lat=$(curl -sG "$PROM" \
    --data-urlencode 'query=sum by (pod) (rate(istio_request_duration_milliseconds_sum{request_protocol="grpc", reporter="source"}[1m])) / sum by (pod) (rate(istio_request_duration_milliseconds_count{request_protocol="grpc", reporter="source"}[1m]))')

  # ---- KUBERNETES DATA ----

  pod_info=$(kubectl get pod -n "$NAMESPACE" -o wide --no-headers | awk '{print $1,$6,$7}')
  top_info=$(kubectl top pod -n "$NAMESPACE" --no-headers 2>/dev/null | awk '{print $1,$2,$3}')

  # Lookup helper
  get_val() {
    printf "%s" "$(echo "$1" | jq -r --arg POD "$pod" '.data.result[]? | select(.metric.pod==$POD) | .value[1]')"
  }

  # ---- PROCESS ALL PODS ----

  while read -r pod ip node; do
    http_r=$(get_val "$http_rpm")
    http_lat_ms=$(get_val "$http_lat")

    grpc_in=$(get_val "$grpc_in_rpm")
    grpc_in_lat_ms=$(get_val "$grpc_in_lat")

    grpc_out=$(get_val "$grpc_out_rpm")
    grpc_out_lat_ms=$(get_val "$grpc_out_lat")

    cpu_mem=$(echo "$top_info" | awk -v p="$pod" '$1==p {print $2 "/" $3}')

    threads=$(kubectl exec -n "$NAMESPACE" "$pod" -- sh -c \
      'grep "^Threads:" /proc/1/status' 2>/dev/null | awk '{print $2}')

    printf "%-38s %-15s %-15s %-9s %-8s %-8s %-8s %-8s %-8s %-12s %-6s\n" \
      "$pod" "$ip" "$node" \
      "$(round1 "$http_r")" "$(round1 "$http_lat_ms")" \
      "$(round1 "$grpc_in")" "$(round1 "$grpc_in_lat_ms")" \
      "$(round1 "$grpc_out")" "$(round1 "$grpc_out_lat_ms")" \
      "${cpu_mem:-N/A}" "${threads:-N/A}"

  done <<< "$pod_info"

  echo ""
  sleep $INTERVAL
done

