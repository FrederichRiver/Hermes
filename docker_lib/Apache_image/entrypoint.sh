#!/bin/bash
set -e

# 在启动前对挂载的源码目录权限进行调整
mkdir -p /var/www/html/static
mkdir -p /var/www/html/media
# Detect Apache runtime user (common: www-data on Debian/Ubuntu, daemon on httpd official image)
APACHE_USER=""
APACHE_GROUP=""
if id -u www-data >/dev/null 2>&1; then
	APACHE_USER=www-data
	APACHE_GROUP=www-data
elif id -u daemon >/dev/null 2>&1; then
	APACHE_USER=daemon
	APACHE_GROUP=daemon
else
	# fallback to current user's uid/gid
	APACHE_USER=$(stat -c '%U' /usr/local/apache2 2>/dev/null || echo root)
	APACHE_GROUP=$(stat -c '%G' /usr/local/apache2 2>/dev/null || echo root)
fi

echo "Adjusting ownership to ${APACHE_USER}:${APACHE_GROUP}"
chown -R ${APACHE_USER}:${APACHE_GROUP} /var/www/html/static || true
chown -R ${APACHE_USER}:${APACHE_GROUP} /var/www/html/media || true
chown -R ${APACHE_USER}:${APACHE_GROUP} /var/log/apache2 || true

# 确保全局 ServerName 存在以抑制 AH00558 警告
: ${APACHE_SERVER_NAME:=localhost}
echo "Setting ServerName to ${APACHE_SERVER_NAME}"
# 在 Debian/Ubuntu Apache 中，添加或替换 /etc/apache2/apache2.conf 中的 ServerName 条目
if grep -q "^ServerName" /etc/apache2/apache2.conf; then
	sed -ri "s/^ServerName.*/ServerName ${APACHE_SERVER_NAME}/" /etc/apache2/apache2.conf
else
	echo "ServerName ${APACHE_SERVER_NAME}" >> /etc/apache2/apache2.conf
fi

# 启用站点并重载配置（确保 sites-available 中的 000-default.conf 可用）
a2ensite 000-default.conf || true

echo "Starting Apache in foreground..."
exec apache2ctl -D FOREGROUND