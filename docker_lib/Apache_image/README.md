docker-compose up -d --build
docker exec -it apache_django_server bash
# Apache + Django Docker (Ubuntu Apache2 + mod_wsgi)

本目录包含用于在容器中运行 Apache2 + mod_wsgi 托管最小 Django 应用的镜像与 Compose 配置。主要目标是：
- 采用 Debian/Ubuntu 风格的 `apache2`（而非官方 `httpd` 镜像）以避免路径/模块差异。
- 使用命名卷 `web_data` 来存放网站内容，避免 Windows 主机直接绑定导致的 `chown` 问题。
- WSGI 仅挂载在 `/application`，静态文件由 Apache 直接提供。

主要文件说明
- `Dockerfile` — 构建镜像（Ubuntu、apache2、libapache2-mod-wsgi-py3、创建虚拟环境、复制 `www/`）。
- `docker-compose.yml` — 定义 `apache_django` 服务，使用命名卷 `web_data:/var/www/html`，并挂载 `apache-django.conf`。
- `entrypoint.sh` — 启动脚本：创建静态/媒体目录、修正权限、设置全局 `ServerName`、启用站点并启动 Apache。
- `apache-django.conf` — 虚拟主机配置：`Alias /static`、`Alias /media`、WSGI 挂载为 `/application`。
- `www/` — 最小 Django App（`manage.py`、`application/` 包、`requirements.txt`）。
- `skill_apache.md` — 本次更改的详细说明与中英注释（已包含）。

快速启动（推荐在 WSL 或 Linux 环境运行）

1) 清理旧容器并构建/启动：

```bash
# 在仓库根目录运行
docker compose -f ./Apache_image/docker-compose.yml down -v
docker compose -f ./Apache_image/docker-compose.yml up -d --build
docker compose -f ./Apache_image/docker-compose.yml logs -f apache_django
```

2) 访问 WSGI 应用（浏览器或 curl）：

```bash
curl http://localhost/application/ --fail --max-time 5
```

注意（Windows 用户）
- 避免将宿主 Windows 路径直接绑定到 `/var/www/html`，这会导致容器内 `chown` 无法生效。当前配置使用命名卷以避免该问题。
- 如果你需要将项目文件放在宿主上进行开发，请使用 WSL 路径或确保宿主目录的权限对容器可读写，并将文件复制到宿主绑定目录中。

常见问题排查
- 如果日志包括 `Target WSGI script not found`：说明容器内未找到 `/var/www/html/application/wsgi.py`，可能是因为宿主绑定覆盖了镜像内容或文件未复制到卷中。
- 检查 Apache 配置语法：
```bash
docker exec -it apache_django_server bash -c "apache2ctl -t"
```
- 查看错误日志：
```bash
docker exec -it apache_django_server bash -c "tail -n 200 /var/log/apache2/error.log"
```
- 检查应用文件与权限：
```bash
docker exec -it apache_django_server bash -c "ls -la /var/www/html /var/www/html/application; stat -c '%U:%G' /var/www/html/application/wsgi.py"
```

可选调整
- 若需同时支持 `/application` 与 `/application/`，在 `apache-django.conf` 同时添加：
```
WSGIScriptAlias /application /var/www/html/application/wsgi.py
WSGIScriptAlias /application/ /var/www/html/application/wsgi.py
```
- 可在 `docker-compose.yml` 的 `environment` 中设置 `APACHE_SERVER_NAME`（例如 `APACHE_SERVER_NAME=example.com`）以替换默认 `localhost`。

需要我帮你：
- 将 `WSGIScriptAlias /application/` 加入 `apache-django.conf`；
- 或把本 README 提交到 Git（`git add`/`commit`）。

---
（此文件由助手基于当前项目配置自动生成，如需调整内容或语言风格，告知我即可）