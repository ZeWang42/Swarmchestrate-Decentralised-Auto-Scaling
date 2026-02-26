
# replace <ip_addr> and <TOKEN> with the private_ip key and the token key in worker-config.json
#
IP_ADDR=$(jq -r '.private_ip' worker-config.json)
TOKEN=$(jq -r '.token' worker-config.json)

if [ -z "$IP_ADDR" ] || [ -z "$TOKEN" ]; then
  echo "ERROR: private_ip or token not found in worker-config.json"
  exit 1
fi

echo "Joining k3s cluster at ${IP_ADDR}"

curl -sfL https://get.k3s.io | \
K3S_URL="https://${IP_ADDR}:6443" \
K3S_TOKEN="${TOKEN}" \
sh -
