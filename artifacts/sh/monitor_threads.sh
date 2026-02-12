#!/usr/bin/env bash

NAMESPACE="default"      # change if needed
INTERVAL=5               # seconds between checks
LOGFILE="thread-monitor.log"

echo "Monitoring thread count for all pods in namespace: $NAMESPACE"
echo "Logging to: $LOGFILE"
echo "Press Ctrl+C to stop."
echo

while true; do
    echo "===== $(date '+%F %T') =====" | tee -a "$LOGFILE"

    # Get all pod names in the namespace
    PODS=$(kubectl get pods -n "$NAMESPACE" --no-headers -o custom-columns=":metadata.name")

    for POD in $PODS; do
        echo -n "Pod: $POD  -->  " | tee -a "$LOGFILE"

        # Extract thread count from PID 1 inside each container
        THREADS=$(kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'grep "^Threads:" /proc/1/status 2>/dev/null' \
                  | awk '{print $2}')

        if [[ -z "$THREADS" ]]; then
            echo "No data (pod might not be ready)" | tee -a "$LOGFILE"
        else
            echo "Threads = $THREADS" | tee -a "$LOGFILE"
        fi
    done

    echo "" | tee -a "$LOGFILE"
    sleep "$INTERVAL"
done

