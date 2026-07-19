#!/usr/bin/env bash
set -euo pipefail

# Copies project files to /home/fred/Docker_image/MySQL_image
DEST=/home/fred/Docker_image/MySQL_image

mkdir -p "$DEST"
cp -r Dockerfile entrypoint.sh docker-compose.yml my.cnf init.sql .env.example "$DEST/"
chown -R $(id -u):$(id -g) "$DEST"
echo "Files copied to $DEST"
