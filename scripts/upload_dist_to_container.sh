#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIRECTORY="/mnt/Milano/ftp/upload/dist"
DESTINATION_DIRECTORY="/mnt/Milano/src_space/dist"

if [[ ! -d "$SOURCE_DIRECTORY" ]]; then
    echo "Source directory does not exist: $SOURCE_DIRECTORY" >&2
    exit 1
fi

mkdir -p "$DESTINATION_DIRECTORY"

shopt -s dotglob nullglob
items=("$SOURCE_DIRECTORY"/*)

if (( ${#items[@]} == 0 )); then
    echo "No files found in: $SOURCE_DIRECTORY"
    exit 0
fi

for item in "${items[@]}"; do
    cp -a "$item" "$DESTINATION_DIRECTORY/"
    echo "Copied $(basename "$item") to $DESTINATION_DIRECTORY"
done
