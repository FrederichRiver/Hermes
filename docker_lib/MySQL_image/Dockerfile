# Dockerfile for MySQL development image
# Based on official mysql:8.0 per project README
FROM mysql:8.0

ENV TZ=Asia/Shanghai

LABEL maintainer="Fred Monster <hezhiyuan_tju@163.com>"
LABEL org.opencontainers.image.title="mysql_server_image"
LABEL org.opencontainers.image.description="MySQL development image configured for docker-compose with external my.cnf and init SQL"
LABEL org.opencontainers.image.version="8.0"
LABEL org.opencontainers.image.licenses="MIT"

# Copy the custom entrypoint which wraps the upstream entrypoint.
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Expose MySQL port and declare data volume
EXPOSE 3306
VOLUME ["/var/lib/mysql"]

# Lightweight healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD mysqladmin ping -uroot || exit 1

# Use our wrapper entrypoint and keep upstream default command
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Pass only the daemon name as the default CMD so the wrapper receives args as expected
CMD ["mysqld"]
