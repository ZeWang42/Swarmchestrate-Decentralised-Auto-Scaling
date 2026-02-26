# modify the private ip in master-config.json and the run:
PRIVATE_IP=$(jq -r '.private_ip' master-config.json)

if [ -z "$PRIVATE_IP" ]; then
  echo "ERROR: private_ip not found in master-config.json"
  exit 1
fi

echo "Loaded master's private ip: ${PRIVATE_IP}"

# Install k3s master
curl -sfL https://get.k3s.io | \
INSTALL_K3S_EXEC="server --node-ip ${PRIVATE_IP} --advertise-address ${PRIVATE_IP}" \
sh -

# Wait until k3s is ready
echo "Waiting for k3s to be ready..."
sleep 1

# Extract token (requires sudo)
sudo cat /var/lib/rancher/k3s/server/node-token > token.txt

echo "Token saved to token.txt"

