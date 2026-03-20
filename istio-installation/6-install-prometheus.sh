cd istio-*
kubectl apply -f samples/addons/prometheus.yaml
kubectl -n default annotate svc waypoint \
  prometheus.io/scrape="true" \
  prometheus.io/port="15020" \
  prometheus.io/path="/stats/prometheus"
