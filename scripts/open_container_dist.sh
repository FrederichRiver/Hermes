#!/usr/bin/env bash
set -euo pipefail

exec docker exec -it \
    -w /home/fred/Downloads/dist \
    app_server_1 \
    /bin/bash
