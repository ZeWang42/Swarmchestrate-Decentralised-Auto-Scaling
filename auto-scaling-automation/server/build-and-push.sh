#!/bin/bash

set -e

# ===== CONFIG =====
IMAGE_NAME="autoscaler-server"
TAG="latest"
REGISTRY="docker.io"
USERNAME="zewang42"

FULL_IMAGE="${REGISTRY}/${USERNAME}/${IMAGE_NAME}:${TAG}"

# ===== BUILD =====
echo "Building image: $FULL_IMAGE"
docker build -t $FULL_IMAGE .

# ===== LOGIN =====
echo "Logging into Docker registry..."
docker login

# ===== PUSH =====
echo "Pushing image: $FULL_IMAGE"
docker push $FULL_IMAGE

echo "Done!"
echo "Image pushed: $FULL_IMAGE"
