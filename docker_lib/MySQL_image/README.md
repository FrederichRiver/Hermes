# MySQL Docker Compose 配置

版本：1.0

## 概览
- 本项目提供了一个可复现的 MySQL 开发镜像和 docker compose 配置。
- 该Docker镜像基于官方 `mysql:8.0` 镜像。

## 文件说明
- `docker-compose.yml` - Compose 配置（构建本地 `Dockerfile`，镜像标签示例为 `mysql-server-image:8.0`）。
- `Dockerfile` - 基于 `mysql:8.0` 官方镜像的自定义构建文件，包含时区设置、健康检查。
- `my.cnf` - 示例 MySQL 配置（挂载到容器的 `/etc/mysql/conf.d/my.cnf`）。
- `init.sql` - 首次容器启动时执行的初始化 SQL 示例。
- `.env.example` - 环境变量示例文件（复制为 `.env` 并填写真实凭证）。

## 功能实现

1. 通过外部的 `.env` 文件注入环境变量，包括初始数据库、用户、密码等。
2. 使用外部挂载的数据卷（`MYSQL_DATA_DIR`）来存储 MySQL 数据目录。地址为`/mnt/Frankfort/mysql_data`，可在 `.env` 中配置为宿主机的绝对路径。
3. 使用 `my.cnf` 挂载到容器的 `/etc/mysql/conf.d/my.cnf`，以覆盖默认配置。
4. 使用 `init.sql` 挂载到容器的 `/docker-entrypoint-initdb.d/init.sql`，在首次启动时执行初始化 SQL。
5. 自定义entrypoint。
6. 自定义network，名称为 `mysql_network`，以便与其他容器通信。
7. 在此项目根目录下，为我生成bash脚本，作用为将相关文件复制到`/home/fred/Docker_image/MySQL_image`下面。

联系方式
- 维护人：Fred Monster
