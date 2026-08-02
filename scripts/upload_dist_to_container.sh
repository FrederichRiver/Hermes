#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIRECTORY="/mnt/Frankfort/ftp/upload/dist"
CONTAINER_NAME="app_server_1"
DESTINATION_DIRECTORY="/home/fred/Downloads/dist"

if [[ ! -d "$SOURCE_DIRECTORY" ]]; then
    echo "Source directory does not exist: $SOURCE_DIRECTORY" >&2
    exit 1
fi

shopt -s nullglob
packages=("$SOURCE_DIRECTORY"/*.tar.gz)
if (( ${#packages[@]} == 0 )); then
    echo "No tar.gz packages found in: $SOURCE_DIRECTORY" >&2
    exit 1
fi

docker exec "$CONTAINER_NAME" mkdir -p "$DESTINATION_DIRECTORY"

for package in "${packages[@]}"; do
    docker cp "$package" "$CONTAINER_NAME:$DESTINATION_DIRECTORY/"
    echo "Copied $(basename "$package") to $CONTAINER_NAME:$DESTINATION_DIRECTORY"
done
