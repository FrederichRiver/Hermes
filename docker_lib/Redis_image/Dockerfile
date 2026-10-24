# Ubuntu/Debian
FROM redis:latest

# 复制自定义配置文件
COPY redis.conf /usr/local/etc/redis/redis.conf
COPY docker-entrypoint.sh /usr/local/bin/redis-entrypoint.sh
RUN chmod 0755 /usr/local/bin/redis-entrypoint.sh

# 暴露端口
EXPOSE 6379

WORKDIR /opt/redis
ENTRYPOINT ["/usr/local/bin/redis-entrypoint.sh"]
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]