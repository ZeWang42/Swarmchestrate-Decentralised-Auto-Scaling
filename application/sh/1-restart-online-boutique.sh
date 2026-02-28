sudo kubectl delete -f ../yaml/online-boutique.yaml
sudo kubectl delete -f ../yaml/hpa-online-boutique.yaml
sudo kubectl apply -f ../yaml/online-boutique.yaml
sudo kubectl apply -f ../yaml/frontend-gateway.yaml
sudo kubectl port-forward -n default svc/frontend-gateway-istio 8080:80 --address 0.0.0.0 &
