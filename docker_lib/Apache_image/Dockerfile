FROM ubuntu:24.04

# 设置环境变量，保持无交互安装及日志无缓冲
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

RUN sed -i 's|http://archive.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources \
    && sed -i 's|http://security.ubuntu.com/ubuntu/|http://mirrors.aliyun.com/ubuntu/|g' /etc/apt/sources.list.d/ubuntu.sources

# 安装 Apache2、Python 及依赖（Ubuntu 布局：/etc/apache2）
RUN apt-get update && apt-get install -y \
    apache2 \
    python3 \
    python3-full \
    python3-pip \
    python3-venv \
    libapache2-mod-wsgi-py3 \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Ensure Apache MPM is available and enable a suitable MPM (mpm_event) at build time.
# Use a2enmod/a2dismod to enable mpm_event and disable conflicting MPMs.
RUN apt-get update && apt-get install -y --no-install-recommends apache2 apache2-bin \
    && a2dismod mpm_prefork || true \
    && a2dismod mpm_worker || true \
    && a2enmod mpm_event || true \
    && apache2ctl -t || true

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 设置工作目录（顶级 web 根，避免过深层级）
WORKDIR /var/www/html

# 复制项目代码到镜像
COPY ./application/ /var/www/html/
COPY ./application/requirements.txt /tmp/requirements.txt

# 为 Python 环境创建一个虚拟环境并使用该 venv 安装依赖
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN /opt/venv/bin/python -m pip install --upgrade pip setuptools wheel
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

# 启用必要模块（由 Debian/Ubuntu 的 apache2 管理）
RUN a2enmod wsgi rewrite headers
# Enable WebDAV modules if any site references DavLockDB or WebDAV features
RUN a2enmod dav dav_fs dav_lock || true
# 复制启动脚本并赋予执行权限
# 复制启动脚本并赋予执行权限
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# 将站点配置复制到 apache sites-available（默认站点）
COPY apache-django.conf /etc/apache2/sites-available/000-default.conf
RUN chown root:root /etc/apache2/sites-available/000-default.conf

# 确保 Apache 日志目录归属为非特权用户 daemon
# 日志目录权限将在容器启动时由 entrypoint 脚本调整（根据镜像中的实际 Apache 运行用户）。

# 暴露 80 端口
EXPOSE 80

# 使用自定义脚本启动 Apache（entrypoint 会以 apache2 命令前台运行）
CMD ["/usr/local/bin/entrypoint.sh"]