#!/bin/sh
set -e

# Wrapper entrypoint for the official MySQL image.
# - Attempts to chown the data dir but tolerates failure (useful for Windows bind mounts).
# - If the data dir is empty, perform an insecure initialization so init SQL runs.
# - Finally exec the upstream entrypoint/CMD.

DATADIR=/var/lib/mysql

echo "[entrypoint] ensure data directory exists: $DATADIR"
mkdir -p "$DATADIR"

echo "[entrypoint] attempting to set ownership to mysql:mysql"
if chown -R mysql:mysql "$DATADIR" 2>/dev/null; then
  echo "[entrypoint] ownership set to mysql:mysql"
else
  echo "[entrypoint] warning: chown not permitted; continuing without changing ownership"
fi

# If directory is empty, initialize database non-securely so that init scripts run
if [ -z "$(ls -A "$DATADIR")" ]; then
  echo "[entrypoint] data directory empty — initializing database"
  # Use upstream initialization binary if available
  if command -v mysqld >/dev/null 2>&1; then
    mysqld --initialize-insecure --user=mysql --datadir="$DATADIR"
  fi
fi

# If user provided arguments, pass them through; else default to provided CMD
if [ "$#" -gt 0 ]; then
  echo "[entrypoint] exec: $@"
  exec "$@"
else
  echo "[entrypoint] exec default: /entrypoint.sh mysqld"
  exec /entrypoint.sh mysqld
fi
