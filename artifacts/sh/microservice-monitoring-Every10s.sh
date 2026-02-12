rm monitorResults.log
while true; do
  echo "[$(date '+%F %T')]" | tee -a monitorResults.log
  ./microservice-monitoring.sh | tee -a monitorResults.log
  echo "" | tee -a monitorResults.log
  sleep 4
done

