#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIRECTORY="/mnt/Milano/ftp/upload/src"
DESTINATION_DIRECTORY="/mnt/Milano/src_space"

if [[ ! -d "$SOURCE_DIRECTORY" ]]; then
    echo "Source directory does not exist: $SOURCE_DIRECTORY" >&2
    exit 1
fi

mkdir -p "$DESTINATION_DIRECTORY"
cp -a "$SOURCE_DIRECTORY/." "$DESTINATION_DIRECTORY/"

echo "Deployed source contents from $SOURCE_DIRECTORY to $DESTINATION_DIRECTORY"
