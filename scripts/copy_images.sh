#!/usr/bin/env bash
set -euo pipefail

# Copy three image folders from source to destination and report success.
SRC_BASE="/mnt/Milano/ftp/upload"
DST_BASE="/home/fred/Docker_image"

FOLDERS=("Apache_image" "MySQL_image" "Ubuntu_image")

mkdir -p "$DST_BASE"

for name in "${FOLDERS[@]}"; do
  src="$SRC_BASE/$name"
  dst="$DST_BASE/$name"

  if [ ! -d "$src" ]; then
    echo "Source folder not found: $src" >&2
    continue
  fi

  # Remove existing dst to ensure a fresh copy
  if [ -e "$dst" ]; then
    rm -rf "$dst"
  fi

  cp -a "$src" "$DST_BASE/" && echo "Copied $name to $dst successfully." || echo "Failed to copy $name." >&2
done

echo "Done."
