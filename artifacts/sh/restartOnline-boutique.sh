sudo kubectl delete -f ../yaml/online-boutique.yaml
sudo kubectl delete -f ../yaml/hpa-online-boutique.yaml
sudo kubectl apply -f ../yaml/online-boutique.yaml
sudo kubectl apply -f ../yaml/frontend-gateway.yaml
