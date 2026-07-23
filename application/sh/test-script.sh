#!/bin/bash

# Configuration
PROM="http://localhost:9090/api/v1/query"
SVC="details-v1"
#SVC="productpage-v1"
WINDOW="2m"

echo "Analyzing Istio Ambient Metrics for: $SVC"
echo "------------------------------------------------------"

# 1. LATENCY (Average time for the full Request-Response cycle)
# We use the 'waypoint' reporter as found in your Prometheus discovery
query_lat="sum(rate(istio_request_duration_milliseconds_sum{reporter=\"waypoint\", destination_workload=\"$SVC\"}[$WINDOW])) / sum(rate(istio_request_duration_milliseconds_count{reporter=\"waypoint\", destination_workload=\"$SVC\"}[$WINDOW]))"

lat_val=$(curl -sG "$PROM" --data-urlencode "query=$query_lat" 2>/dev/null | jq -r '.data.result[0].value[1]')

# 2. RPM (Requests Per Minute)
query_rpm="sum(rate(istio_requests_total{reporter=\"waypoint\", destination_workload=\"$SVC\"}[$WINDOW])) * 60"

rpm_val=$(curl -sG "$PROM" --data-urlencode "query=$query_rpm" 2>/dev/null | jq -r '.data.result[0].value[1]')

# 3. CONCURRENCY (Calculated via Little's Law: L = λ * W)
# Convert RPM to RPS (λ) and Latency to Seconds (W)
if [[ "$lat_val" != "null" && "$rpm_val" != "null" ]]; then
    rps=$(echo "scale=4; $rpm_val / 60" | bc)
    lat_sec=$(echo "scale=4; $lat_val / 1000" | bc)
    concurrency=$(echo "scale=2; $rps * $lat_sec" | bc)
else
    concurrency="0.00"
fi

# Clean up null values for display
lat_display=${lat_val:-0.00}
rpm_display=${rpm_val:-0.0}

# Display Results
printf "%-20s | %-20s\n" "METRIC" "VALUE (WAYPOINT)"
printf "%-20s | %-20s\n" "--------------------" "--------------------"
printf "%-20s | %-20.2f ms\n" "Latency (W)" "$lat_display"
printf "%-20s | %-20.1f\n" "Throughput (RPM)" "$rpm_display"
printf "%-20s | %-20.2f requests\n" "Concurrency (L)" "$concurrency"

echo "------------------------------------------------------"
echo "Note: Concurrency (L) represents active 'in-flight' requests."
echo "If Latency is high, Concurrency represents the Queue Length."

