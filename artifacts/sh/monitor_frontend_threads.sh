#!/usr/bin/env bash

POD="frontend-5c7dfbfd5d-66xlg"
NAMESPACE="default"   # change if it's in another namespace
INTERVAL=5            # seconds between samples

while true; do
  echo "[$(date '+%F %T')] Pod: $POD"
  # Threads of the main process (PID 1) inside the container
  kubectl exec -n "$NAMESPACE" "$POD" -- sh -c 'grep "^Threads:" /proc/1/status' || echo "kubectl exec failed"
  echo
  sleep "$INTERVAL"
done

