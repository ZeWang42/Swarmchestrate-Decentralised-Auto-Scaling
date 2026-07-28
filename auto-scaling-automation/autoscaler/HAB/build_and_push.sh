#!/usr/bin/env bash
set -euo pipefail

IMAGE_NAME="zewang42/hab-autoscaler"
TAG="${1:-latest}"

echo "Building ${IMAGE_NAME}:${TAG}..."

docker build --platform linux/amd64 -t "${IMAGE_NAME}:${TAG}" .

echo "Pushing ${IMAGE_NAME}:${TAG}..."
docker push "${IMAGE_NAME}:${TAG}"

echo "Done: ${IMAGE_NAME}:${TAG}"
