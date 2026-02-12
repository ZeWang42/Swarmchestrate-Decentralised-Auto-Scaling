#!/usr/bin/env bash

NAMESPACE="default"
INTERVAL=5
LOG="tcp-monitor.log"

echo "Monitoring TCP backlog + queue length for namespace: $NAMESPACE"
echo "Log: $LOG"
echo "Press Ctrl+C to stop."
echo

while true; do
  echo "===== $(date '+%F %T') =====" | tee -a "$LOG"

  PODS=$(kubectl get pods -n $NAMESPACE --no-headers -o custom-columns=":metadata.name")

  for POD in $PODS; do
    echo "Pod: $POD" | tee -a "$LOG"

    # --- Queue length / concurrency ---
    kubectl exec -n $NAMESPACE $POD -- sh -c "grep '^TCP:' /proc/net/sockstat" \
      | tee -a "$LOG"


    # --- Extract only overload-related counters ---
    kubectl exec -n $NAMESPACE $POD -- sh -c "
      cat /proc/net/netstat 2>/dev/null | grep TcpExt | tail -1 |
      awk '{
        print \
          \"ListenOverflows=\" \$20, \
          \"ListenDrops=\" \$21, \
          \"TCPBacklogDrop=\" \$78, \
          \"TCPTimeouts=\" \$41, \
          \"TCPFastRetrans=\" \$37, \
          \"TCPLossProbes=\" \$42, \
          \"TCPSlowStartRetrans=\" \$38, \
          \"TCPAbortOnTimeout=\" \$55, \
          \"TCPRcvQDrop=\" \$92
        }'
    " | tee -a "$LOG"

    echo | tee -a "$LOG"
  done

  sleep $INTERVAL
done

