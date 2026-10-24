#!/usr/bin/env bash
set -euo pipefail
umask 077

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ubuntu_env_file="$repo_root/docker_lib/Ubuntu_image/.env.secrets"
redis_env_file="$repo_root/docker_lib/Redis_image/.env.secrets"
webui_env_file="$repo_root/docker_lib/Apache_image/.env.secrets"

for env_file in "$ubuntu_env_file" "$redis_env_file" "$webui_env_file"; do
    if [[ -e "$env_file" ]]; then
        printf 'Refusing to overwrite existing environment file: %s\n' "$env_file" >&2
        exit 1
    fi
done

if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required to generate Redis and Django secrets." >&2
    exit 1
fi

redis_username="${REDIS_USERNAME:-hermes}"
if [[ ! "$redis_username" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "REDIS_USERNAME may contain only letters, digits, underscores, and hyphens." >&2
    exit 1
fi

redis_password="${REDIS_PASSWORD:-$(openssl rand -hex 32)}"
django_secret_key="${SECRET_KEY:-$(openssl rand -hex 32)}"
redis_url="${REDIS_URL:-redis://172.18.0.7:6379/0}"

quote_env_value() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\'/\\\'}"
    printf "'%s'" "$value"
}

write_env_var() {
    local env_file="$1"
    local name="$2"
    local value="$3"
    printf '%s=%s\n' "$name" "$(quote_env_value "$value")" >> "$env_file"
}

temp_dir="$(mktemp -d)"
cleanup() {
    rm -rf "$temp_dir"
}
trap cleanup EXIT

ubuntu_temp_file="$temp_dir/ubuntu.env"
redis_temp_file="$temp_dir/redis.env"
webui_temp_file="$temp_dir/webui.env"
: > "$ubuntu_temp_file"
: > "$redis_temp_file"
: > "$webui_temp_file"

write_env_var "$ubuntu_temp_file" REDIS_URL "$redis_url"
write_env_var "$ubuntu_temp_file" REDIS_USERNAME "$redis_username"
write_env_var "$ubuntu_temp_file" REDIS_PASSWORD "$redis_password"
write_env_var "$ubuntu_temp_file" SERVER_NAME "${SERVER_NAME:-Ubuntu_docker}"
write_env_var "$ubuntu_temp_file" MYSQL_HOST "${MYSQL_HOST:-172.18.0.2}"
write_env_var "$ubuntu_temp_file" MYSQL_PORT "${MYSQL_PORT:-3306}"
write_env_var "$ubuntu_temp_file" MYSQL_USERNAME "${MYSQL_USERNAME:-stock}"
write_env_var "$ubuntu_temp_file" MYSQL_PASSWORD "${MYSQL_PASSWORD:-}"
write_env_var "$ubuntu_temp_file" DB_HOST "${DB_HOST:-${MYSQL_HOST:-172.18.0.2}}"
write_env_var "$ubuntu_temp_file" DB_PORT "${DB_PORT:-${MYSQL_PORT:-3306}}"
write_env_var "$ubuntu_temp_file" LOG_LEVEL "${LOG_LEVEL:-INFO}"
write_env_var "$ubuntu_temp_file" SSE_FETCH_INTERVAL_SECONDS "${SSE_FETCH_INTERVAL_SECONDS:-3600}"
write_env_var "$ubuntu_temp_file" REDIS_STREAM_NAME "${REDIS_STREAM_NAME:-market:listings:sse}"
write_env_var "$ubuntu_temp_file" SMTP_HOST "${SMTP_HOST:-}"
write_env_var "$ubuntu_temp_file" SMTP_PORT "${SMTP_PORT:-587}"
write_env_var "$ubuntu_temp_file" SMTP_USERNAME "${SMTP_USERNAME:-}"
write_env_var "$ubuntu_temp_file" SMTP_PASSWORD "${SMTP_PASSWORD:-}"
write_env_var "$ubuntu_temp_file" SMTP_SENDER "${SMTP_SENDER:-}"
write_env_var "$ubuntu_temp_file" SMTP_RECIPIENT "${SMTP_RECIPIENT:-}"
write_env_var "$ubuntu_temp_file" SMTP_USE_STARTTLS "${SMTP_USE_STARTTLS:-true}"
write_env_var "$ubuntu_temp_file" IMAP_HOST "${IMAP_HOST:-}"
write_env_var "$ubuntu_temp_file" IMAP_PORT "${IMAP_PORT:-993}"
write_env_var "$ubuntu_temp_file" IMAP_USERNAME "${IMAP_USERNAME:-}"
write_env_var "$ubuntu_temp_file" IMAP_PASSWORD "${IMAP_PASSWORD:-}"
write_env_var "$ubuntu_temp_file" IMAP_MAILBOX "${IMAP_MAILBOX:-INBOX}"

write_env_var "$redis_temp_file" REDIS_USERNAME "$redis_username"
write_env_var "$redis_temp_file" REDIS_PASSWORD "$redis_password"

write_env_var "$webui_temp_file" SECRET_KEY "$django_secret_key"
write_env_var "$webui_temp_file" DJANGO_SETTINGS_MODULE "${DJANGO_SETTINGS_MODULE:-application.settings}"
write_env_var "$webui_temp_file" DJANGO_DEBUG "${DJANGO_DEBUG:-false}"
write_env_var "$webui_temp_file" DB_NAME "${DB_NAME:-website}"
write_env_var "$webui_temp_file" DB_USER "${DB_USER:-www}"
write_env_var "$webui_temp_file" DB_PASSWORD "${DB_PASSWORD:-}"
write_env_var "$webui_temp_file" DB_HOST "${DB_HOST:-172.18.0.2}"
write_env_var "$webui_temp_file" DB_PORT "${DB_PORT:-3306}"

chmod 600 "$ubuntu_temp_file" "$redis_temp_file" "$webui_temp_file"
mv "$ubuntu_temp_file" "$ubuntu_env_file"
mv "$redis_temp_file" "$redis_env_file"
mv "$webui_temp_file" "$webui_env_file"

printf 'Created protected Docker environment files:\n  %s\n  %s\n  %s\n' \
    "$ubuntu_env_file" "$redis_env_file" "$webui_env_file"
echo "Start or recreate the services with Docker Compose to apply the new variables."
