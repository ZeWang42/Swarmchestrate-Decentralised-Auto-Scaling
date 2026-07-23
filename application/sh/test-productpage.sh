#!/bin/bash

# Configuration
PROM="http://localhost:9090/api/v1/query"
SVC_NAME="productpage" # Using Service Name instead of Workload Name
WINDOW="2m"

echo "Analyzing Istio Ambient Metrics for: $SVC_NAME"
echo "------------------------------------------------------"

# 1. LATENCY (W)
query_lat="sum(rate(istio_request_duration_milliseconds_sum{destination_service_name=\"$SVC_NAME\"}[$WINDOW])) / sum(rate(istio_request_duration_milliseconds_count{destination_service_name=\"$SVC_NAME\"}[$WINDOW]))"

lat_val=$(curl -s -G "$PROM" --data-urlencode "query=$query_lat" | jq -r '.data.result[0].value[1]')

# 2. RPM (Throughput)
query_rpm="sum(rate(istio_requests_total{destination_service_name=\"$SVC_NAME\"}[$WINDOW])) * 60"

rpm_val=$(curl -s -G "$PROM" --data-urlencode "query=$query_rpm" | jq -r '.data.result[0].value[1]')

# 3. CONCURRENCY (L) CALCULATION
# Use [[ ]] and check for numeric values to prevent syntax errors
if [[ "$lat_val" =~ ^[0-9.]+$ && "$rpm_val" =~ ^[0-9.]+$ ]]; then
    rps=$(echo "scale=4; $rpm_val / 60" | bc)
    lat_sec=$(echo "scale=4; $lat_val / 1000" | bc)
    concurrency=$(echo "scale=2; $rps * $lat_sec" | bc)
else
    lat_val="0.00"
    rpm_val="0.0"
    concurrency="0.00"
fi

# Display Results
printf "%-20s | %-20s\n" "METRIC" "VALUE"
printf "%-20s | %-20s\n" "--------------------" "--------------------"
printf "%-20s | %-20.2f ms\n" "Latency (W)" "$lat_val"
printf "%-20s | %-20.1f\n" "Throughput (RPM)" "$rpm_val"
printf "%-20s | %-20.2f requests\n" "Concurrency (L)" "$concurrency"

echo "------------------------------------------------------"

