#!/bin/sh
set -eu

: "${REDIS_USERNAME:?REDIS_USERNAME must be set}"
: "${REDIS_PASSWORD:?REDIS_PASSWORD must be set}"

case "$REDIS_USERNAME" in
  *[!A-Za-z0-9_-]*)
    echo "REDIS_USERNAME may contain only letters, digits, underscores, and hyphens." >&2
    exit 1
    ;;
esac

if [ "$REDIS_USERNAME" = "default" ]; then
  echo "REDIS_USERNAME must not be the reserved default user." >&2
  exit 1
fi

password_hash="$(printf '%s' "$REDIS_PASSWORD" | sha256sum | cut -d ' ' -f 1)"
acl_file="/run/redis-users.acl"
printf 'user %s on #%s ~* &event:* +@all\n' "$REDIS_USERNAME" "$password_hash" > "$acl_file"
chmod 0600 "$acl_file"

exec "$@"
