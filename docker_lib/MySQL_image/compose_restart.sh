#!/usr/bin/env bash
set -euo pipefail

# Compose restart helper: stops the stack, rebuilds images, and starts in detached mode.
# Usage: ./compose_restart.sh

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

echo "Stopping any running compose services..."
docker compose down --remove-orphans

echo "Building and starting services..."
docker compose up -d --build

echo "Done. Showing compose ps:"
docker compose ps
