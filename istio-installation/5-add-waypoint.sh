istioctl waypoint apply -n default --enroll-namespace
kubectl label namespace default istio.io/use-waypoint=waypoint
sudo kubectl port-forward -n default svc/frontend-gateway-istio 8080:80 --address 0.0.0.0 &
