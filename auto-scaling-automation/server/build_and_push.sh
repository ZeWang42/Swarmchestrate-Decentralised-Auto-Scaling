#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="zewang42/autoscaling-experiment-server"
TAG="${1:-latest}"

echo "Building ${IMAGE_NAME}:${TAG} for linux/amd64..."

docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" .

echo "Pushing ${IMAGE_NAME}:${TAG}..."
docker push "${IMAGE_NAME}:${TAG}"

echo "Done: ${IMAGE_NAME}:${TAG}"
