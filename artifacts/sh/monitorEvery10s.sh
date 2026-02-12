rm monitorResults.log
while true; do
  echo "[$(date '+%F %T')]" | tee -a monitorResults.log
  ./monitor.sh | tee -a monitorResults.log
  echo "" | tee -a monitorResults.log
  sleep 6
done

