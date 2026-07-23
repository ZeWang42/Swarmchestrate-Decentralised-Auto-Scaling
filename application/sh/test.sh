#!/usr/bin/env bash

export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

NAMESPACE="default"
INTERVAL=5
PROM="http://localhost:9090/api/v1/query"
SOURCE_WL="productpage-v1"
SOURCE_APP="productpage"

round1() {
  if [[ -z "$1" || "$1" == "null" || "$1" == "NaN" ]]; then
    printf "0.0"
  else
    printf "%.1f" "$1"
  fi
}

prom_query() {
  local query="$1"
  curl -sG "$PROM" \
    --data-urlencode "query=$query" 2>/dev/null | jq -r '.data.result[0].value[1] // "0"'
}

prom_multi() {
  local query="$1"
  curl -sG "$PROM" \
    --data-urlencode "query=$query" 2>/dev/null | jq -r '
      .data.result[]? |
      [
        (.metric.destination_workload // .metric.source_workload // "unknown"),
        (.value[1] // "0")
      ] | @tsv
    '
}

while true; do
  clear
  echo "=== Ambient Mesh Monitor: productpage focus ==="
  echo "Namespace   : $NAMESPACE"
  echo "Prometheus  : $PROM"
  echo "Source WL   : $SOURCE_WL"
  echo "Time        : $(date '+%F %T')"
  echo ""

  #
  # 1) ALL REQUESTS RECEIVED BY PRODUCTPAGE
  #
  echo "=== Requests received by productpage ==="
  echo "TYPE        RPM       LAT(ms)"
  echo "--------------------------------"

  in_http_rpm=$(prom_query "sum(rate(istio_requests_total{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"http\"}[2m])) * 60")
  in_http_lat=$(prom_query "sum(rate(istio_request_duration_milliseconds_sum{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"http\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"http\"}[2m]))")

  in_grpc_rpm=$(prom_query "sum(rate(istio_requests_total{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"grpc\"}[2m])) * 60")
  in_grpc_lat=$(prom_query "sum(rate(istio_request_duration_milliseconds_sum{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"grpc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{destination_workload=\"$SOURCE_WL\", destination_workload_namespace=\"$NAMESPACE\", request_protocol=\"grpc\"}[2m]))")

  printf "%-10s %-9s %-10s\n" "HTTP" "$(round1 "$in_http_rpm")" "$(round1 "$in_http_lat")"
  printf "%-10s %-9s %-10s\n" "gRPC" "$(round1 "$in_grpc_rpm")" "$(round1 "$in_grpc_lat")"

  #
  # 2) ALL REQUESTS FROM PRODUCTPAGE TO OTHERS
  #
  echo ""
  echo "=== Requests from productpage to downstream services ==="
  echo "DESTINATION          HTTP_RPM  HTTP_LAT   gRPC_RPM  gRPC_LAT"
  echo "------------------------------------------------------------"

  mapfile -t dests < <(
    curl -sG "$PROM" \
      --data-urlencode "query=sum by (destination_workload) (rate(istio_requests_total{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\"}[2m]))" \
      2>/dev/null | jq -r '.data.result[]?.metric.destination_workload' | sort -u
  )

  for dst in "${dests[@]}"; do
    [[ -z "$dst" || "$dst" == "unknown" || "$dst" == "$SOURCE_WL" ]] && continue

    out_http_rpm=$(prom_query "sum(rate(istio_requests_total{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"http\"}[2m])) * 60")
    out_http_lat=$(prom_query "sum(rate(istio_request_duration_milliseconds_sum{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"http\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"http\"}[2m]))")

    out_grpc_rpm=$(prom_query "sum(rate(istio_requests_total{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"grpc\"}[2m])) * 60")
    out_grpc_lat=$(prom_query "sum(rate(istio_request_duration_milliseconds_sum{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"grpc\"}[2m])) / sum(rate(istio_request_duration_milliseconds_count{source_workload=\"$SOURCE_WL\", source_workload_namespace=\"$NAMESPACE\", destination_workload=\"$dst\", request_protocol=\"grpc\"}[2m]))")

    printf "%-20s %-9s %-10s %-9s %-10s\n" \
      "$dst" \
      "$(round1 "$out_http_rpm")" \
      "$(round1 "$out_http_lat")" \
      "$(round1 "$out_grpc_rpm")" \
      "$(round1 "$out_grpc_lat")"
  done

  #
  # 3) PRODUCTPAGE POD RESOURCE SUMMARY
  #
  echo ""
  echo "=== productpage pod resources ==="
  echo "WORKLOAD             CPU(m)    MEM(MiB) PODS"
  echo "--------------------------------------------"

  cpu_raw=$(kubectl top pod -n "$NAMESPACE" 2>/dev/null | grep "$SOURCE_APP" | awk '{gsub("m","",$2); sum+=$2} END {print sum+0}')
  mem_raw=$(kubectl top pod -n "$NAMESPACE" 2>/dev/null | grep "$SOURCE_APP" | awk '{gsub("Mi","",$3); sum+=$3} END {print sum+0}')
  pods=$(kubectl get pod -n "$NAMESPACE" --no-headers 2>/dev/null | grep "$SOURCE_APP" | grep "Running" | wc -l)

  printf "%-20s %-9s %-8s %-5s\n" "$SOURCE_WL" "${cpu_raw:-0}" "${mem_raw:-0}" "${pods:-0}"

  echo ""
  sleep "$INTERVAL"
done
