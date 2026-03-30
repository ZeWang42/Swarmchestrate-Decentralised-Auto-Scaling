kubectl autoscale deployment details-v1 --cpu-percent=80 --min=1 --max=5
kubectl autoscale deployment productpage-v1 --cpu-percent=80 --min=1 --max=5
kubectl autoscale deployment ratings-v1 --cpu-percent=80 --min=1 --max=5
kubectl autoscale deployment reviews-v1 --cpu-percent=80 --min=1 --max=5
kubectl autoscale deployment reviews-v2 --cpu-percent=80 --min=1 --max=5
kubectl autoscale deployment reviews-v3 --cpu-percent=80 --min=1 --max=5

