#!/usr/bin/env bash
# Deploy webui files from FTP upload directory to web server directory
# Usage: sudo ./deploy_sync_webui.sh

set -euo pipefail

SRC="/mnt/Frankfort/ftp/upload/webui/"
DST="/opt/www"
OWNER="www-data:www-data"

if [[ ! -d "$SRC" ]]; then
  echo "Source directory $SRC does not exist. Exiting." >&2
  exit 2
fi

# Ensure destination exists
if [[ ! -d "$DST" ]]; then
  echo "Destination $DST does not exist. Creating..."
  mkdir -p "$DST"
fi

echo "Copying files from $SRC -> $DST using cp"
# Copy files preserving attributes; do NOT remove existing files in destination
echo "Copying (update only) files from $SRC to $DST"
# -u: copy only when SOURCE newer than DEST or DEST missing
# -a: archive mode (preserve attributes)
cp -au "$SRC"* "$DST"/ || true

echo "Setting ownership to $OWNER"
chown -R $OWNER "$DST"

echo "Sync complete."