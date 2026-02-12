#!/bin/bash

# Fetch RPM and latency from Prometheus
rpm_data=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=sum by (instance) (rate(istio_requests_total{destination_workload_namespace="default"}[1m])) * 60' \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

lat_data=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode 'query=(sum by (instance) (rate(istio_request_duration_milliseconds_sum{destination_workload_namespace="default"}[1m])) / sum by (instance) (rate(istio_request_duration_milliseconds_count{destination_workload_namespace="default"}[1m])))' \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# Print header
printf "%-45s %-15s %-15s %-10s %-10s\n" "POD" "IP" "NODE" "RPM" "LAT(ms)"
echo "-------------------------------------------------------------------------------------------------------------"

# Loop over each instance from RPM data
while read instance rpm; do
  ip=${instance%%:*}
  rpm_int=$(printf "%.0f" "$rpm")

  # Get latency for this instance (if available)
  latency=$(echo "$lat_data" | awk -v inst="$instance" '$1 == inst {print $2}')
  latency_ms=$(printf "%.1f" "${latency:-0}")

  # Get Pod + Node info from kubectl
  pod_info=$(sudo kubectl get pod -n default -o wide --no-headers | awk -v ip=$ip '$6==ip {print $1, $7}')
  pod=$(echo "$pod_info" | awk '{print $1}')
  node=$(echo "$pod_info" | awk '{print $2}')

  # Print line
  printf "%-45s %-15s %-15s %-10s %-10s\n" "$pod" "$ip" "$node" "$rpm_int" "$latency_ms"
done <<< "$rpm_data"

