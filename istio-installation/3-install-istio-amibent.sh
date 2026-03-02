
#!/bin/bash
# Dynamically find the istio directory and add it to the path
export PATH=$(pwd)/istio-1.29.0/bin:$PATH

istioctl install --set profile=ambient --set values.global.platform=k3s

