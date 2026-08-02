#!/usr/bin/env sh
# Copy specific Docker image folders from source to destination
# Source: /mnt/Milano/ftp/upload
# Destination: /home/fred/Docker_image

set -u

SRC_BASE="/mnt/Milano/ftp/upload"
DST_BASE="/home/fred/Docker_image"

folders="Apache_image MySQL_image Ubuntu_image"

mkdir -p "$DST_BASE" || {
  echo "Failed to create destination directory: $DST_BASE" >&2
  exit 2
}

for name in $folders; do
  src="$SRC_BASE/$name"
  dst="$DST_BASE/$name"

  if [ ! -d "$src" ]; then
    echo "Source not found: $src" >&2
    continue
  fi

  # Remove existing destination folder to ensure a fresh copy
  if [ -e "$dst" ]; then
    rm -rf "$dst" || {
      echo "Failed to remove existing destination: $dst" >&2
      continue
    }
  fi

  cp -a "$src" "$DST_BASE/" && \
    echo "Copied $name to $DST_BASE successfully." || \
    echo "Failed to copy $name to $DST_BASE" >&2
done

exit 0
