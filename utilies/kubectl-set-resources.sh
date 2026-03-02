# one could use this command to alter reource limits and requests to mimic vertical scaling
# note that this command will terminate and lanch a new pod
kubectl set resources deployment productpage-v1 --limits=cpu=500m,memory=512Mi --requests=cpu=200m,memory=256Mi

