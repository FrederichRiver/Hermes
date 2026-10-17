# Ubuntu/Debian
FROM redis:latest

# 复制自定义配置文件
COPY redis.conf /usr/local/etc/redis/redis.conf

# 暴露端口
EXPOSE 6379

WORKDIR /opt/redis
# 使用自定义配置启动（覆盖默认 CMD）
CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]