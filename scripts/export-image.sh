#!/bin/sh
set -eu
mkdir -p dist
docker buildx build --platform linux/amd64 -t pre-security-copilot:demo --output type=docker,dest=dist/pre-security-copilot-amd64.tar .
cp compose.server.yaml dist/compose.yaml
cp .env.example dist/
shasum -a 256 dist/pre-security-copilot-amd64.tar > dist/SHA256SUMS
