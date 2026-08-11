# Ubuntu/Debian
FROM ubuntu:24.04

RUN apt update && apt install -y redis-server

# 启动并设置开机自启
RUN systemctl enable redis-server
RUN systemctl start redis-server

WORKDIR /etc/redis

CMD ["tail", "-f", "/dev/null"]