

# Extract token (requires sudo)
sudo cat /var/lib/rancher/k3s/server/node-token > token.txt

echo "Token saved to token.txt"
# Bypass sudo
#
sudo chown $USER:$USER /etc/rancher/k3s/k3s.yaml
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
