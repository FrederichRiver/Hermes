#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="/opt/application/log/hermes.log"

if [[ ! -f "$LOG_FILE" ]]; then
    echo "Log file does not exist: $LOG_FILE" >&2
    exit 1
fi

exec tail -n 100 -F "$LOG_FILE"
