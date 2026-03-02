 curl -s "http://localhost:9090/api/v1/query" \
  --get --data-urlencode 'query=sum by (source_workload, destination_workload) (istio_requests_total)' | jq '.data.result[] | {from: .metric.source_workload, to: .metric.destination_workload}'
