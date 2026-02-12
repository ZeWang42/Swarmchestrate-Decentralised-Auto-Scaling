#!/bin/bash
# --- Configuration ------------------------------------------------------------
ns="default"   # namespace to monitor

# --- 1. Prometheus metrics: HTTP ----------------------------------------------
# HTTP Requests per minute
rpm_http=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=sum by (instance) (rate(istio_requests_total{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m])) * 60" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# HTTP Average latency (ms)
lat_http=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=(sum by (instance) (rate(istio_request_duration_milliseconds_sum{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m])) / sum by (instance) (rate(istio_request_duration_milliseconds_count{destination_workload_namespace=\"$ns\", request_protocol=\"http\"}[1m])))" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# --- 2. Prometheus metrics: gRPC ----------------------------------------------
# gRPC Requests per minute
rpm_grpc=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=sum by (instance) (rate(istio_requests_total{destination_workload_namespace=\"$ns\", request_protocol=\"grpc\"}[1m])) * 60" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# gRPC Average latency (ms)
lat_grpc=$(curl -sG 'http://localhost:9090/api/v1/query' \
  --data-urlencode "query=(sum by (instance) (rate(istio_request_duration_milliseconds_sum{destination_workload_namespace=\"$ns\", request_protocol=\"grpc\"}[1m])) / sum by (instance) (rate(istio_request_duration_milliseconds_count{destination_workload_namespace=\"$ns\", request_protocol=\"grpc\"}[1m])))" \
  | jq -r '.data.result[] | "\(.metric.instance)\t\(.value[1])"')

# --- 3. Kubernetes metrics ----------------------------------------------------
# Pod → IP → Node mapping
pod_node_data=$(sudo kubectl get pod -n "$ns" -o wide --no-headers | awk '{print $1,$6,$7}')

# CPU and MEM usage
top_data=$(sudo kubectl top pod -n "$ns" --no-headers 2>/dev/null | awk '{print $1,$2,$3}')

# --- 4. Output ----------------------------------------------------------------
printf "%-45s %-15s %-15s %-10s %-10s %-10s %-10s %-10s\n" \
  "POD" "IP" "NODE" "RPM(HTTP)" "LAT_HTTP(ms)" "RPM(gRPC)" "LAT_gRPC(ms)" "CPU/MEM"
echo "-------------------------------------------------------------------------------------------------------------------------------"

# Combine both HTTP and gRPC datasets (by instance IP)
all_instances=$(printf "%s\n%s\n" "$rpm_http" "$rpm_grpc" | awk '{print $1}' | sort -u)

for instance in $all_instances; do
  ip=${instance%%:*}

  # Match HTTP data
  rpm_h=$(echo "$rpm_http" | awk -v inst="$instance" '$1==inst{print $2}')
  rpm_http_int=$(printf "%.0f" "${rpm_h:-0}")

  lat_h=$(echo "$lat_http" | awk -v inst="$instance" '$1==inst{print $2}')
  lat_http_ms=$(printf "%.1f" "${lat_h:-0}")

  # Match gRPC data
  rpm_g=$(echo "$rpm_grpc" | awk -v inst="$instance" '$1==inst{print $2}')
  rpm_grpc_int=$(printf "%.0f" "${rpm_g:-0}")

  lat_g=$(echo "$lat_grpc" | awk -v inst="$instance" '$1==inst{print $2}')
  lat_grpc_ms=$(printf "%.1f" "${lat_g:-0}")

  # Match pod/node
  pod_info=$(echo "$pod_node_data" | awk -v ip="$ip" '$2==ip{print $1,$3}')
  pod=$(echo "$pod_info" | awk '{print $1}')
  node=$(echo "$pod_info" | awk '{print $2}')

  # CPU and MEM
  top_info=$(echo "$top_data" | awk -v pod="$pod" '$1==pod{print $2,$3}')
  cpu=$(echo "$top_info" | awk '{print $1}')
  mem=$(echo "$top_info" | awk '{print $2}')

  printf "%-45s %-15s %-15s %-10s %-10s %-10s %-10s %-10s\n" \
    "$pod" "$ip" "$node" "$rpm_http_int" "$lat_http_ms" "$rpm_grpc_int" "$lat_grpc_ms" "${cpu:-N/A}/${mem:-N/A}"
done

