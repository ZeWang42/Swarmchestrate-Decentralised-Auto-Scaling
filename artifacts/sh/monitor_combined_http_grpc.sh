#!/bin/bash

ns="default"   # namespace
#ns="kube-system"   # namespace

# --- 1. Prometheus metrics ----------------------------------------------------
# Requests per minute
rpm_data=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=sum by (instance) (rate(istio_requests_total{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m]))" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# Average latency (ms)
lat_data=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=(sum by (instance) (rate(istio_request_duration_milliseconds_sum{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m])) / sum by (instance) (rate(istio_request_duration_milliseconds_count{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m])))" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# Requests currently in flight
inflight_data=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=sum by (instance) (istio_requests_in_flight{destination_workload_namespace=\"$ns\"})" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# --- 2. Kubernetes metrics ----------------------------------------------------
# Pod→Node and IP
pod_node_data=$(sudo kubectl get pod -n "$ns" -o wide --no-headers | awk '{print $1,$6,$7}')

# CPU/MEM usage (kubectl top)
top_data=$(sudo kubectl top pod -n "$ns" --no-headers 2>/dev/null | awk '{print $1,$2,$3}')

# --- 3. Output ----------------------------------------------------------------
printf "%-45s %-15s %-15s %-8s %-10s %-10s %-10s %-10s\n" \
  "POD" "IP" "NODE" "RPM" "LAT(ms)" "INFLIGHT" "CPU(m)" "MEM(Mi)"
echo "--------------------------------------------------------------------------------------------------------------"

while read instance rpm; do
  ip=${instance%%:*}
  rpm_int=$(printf "%.0f" "$rpm")

  latency=$(echo "$lat_data" | awk -v inst="$instance" '$1==inst{print $2}')
  latency_ms=$(printf "%.1f" "${latency:-0}")

  inflight=$(echo "$inflight_data" | awk -v inst="$instance" '$1==inst{print $2}')
  inflight_int=$(printf "%.0f" "${inflight:-0}")

  # match pod name and node by IP
  pod_info=$(echo "$pod_node_data" | awk -v ip="$ip" '$2==ip{print $1,$3}')
  pod=$(echo "$pod_info" | awk '{print $1}')
  node=$(echo "$pod_info" | awk '{print $2}')

  # match CPU/MEM by pod name
  top_info=$(echo "$top_data" | awk -v pod="$pod" '$1==pod{print $2,$3}')
  cpu=$(echo "$top_info" | awk '{print $1}')
  mem=$(echo "$top_info" | awk '{print $2}')

  printf "%-45s %-15s %-15s %-8s %-10s %-10s %-10s %-10s\n" \
    "$pod" "$ip" "$node" "$rpm_int" "$latency_ms" "$inflight_int" "${cpu:-N/A}" "${mem:-N/A}"
done <<< "$rpm_data"
