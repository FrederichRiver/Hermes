# Redis 认证配置定义

## 概述

本文定义 Hermes 服务访问 Redis 时的 ACL（访问控制列表）认证配置。Redis 用户名与密码通过运行环境注入，客户端和 Redis 服务端使用相同配置；凭据不得提交到源码或镜像配置文件。

## 需求

1. 客户端使用 `REDIS_URL` 指定 Redis 地址，使用 `REDIS_USERNAME`、`REDIS_PASSWORD` 分别提供 ACL 用户名和密码。
2. Redis 服务容器从环境变量生成 ACL 配置，不在 `redis.conf` 或镜像层保存密码明文。
3. Redis `default` 用户关闭，只启用配置的 ACL 用户。
4. Compose 在缺少用户名或密码时应明确失败；不得悄悄以未认证方式连接。
5. Ubuntu 应用容器和 Redis 容器从受保护的环境配置中取得同一组 Redis 凭据。
6. 迁移覆盖所有源码中的 Redis 客户端，包括 Event、Data、TimeAgent、WebsiteAgent、`main.py` 和抓取器入口。

## 环境变量

```dotenv
REDIS_USERNAME=fred
REDIS_PASSWORD=<由部署环境提供的强随机密码>
REDIS_URL=redis://172.18.0.7:6379/0
```

生产环境应将这些变量保存在权限受限的环境文件或容器密钥管理机制中，不将真实密码写入仓库。Redis 客户端和服务器必须使用相同用户名、密码。Docker Compose 可用 `--env-file /etc/hermes/redis.env` 为服务端与客户端注入同一组变量；`docker_lib/Redis_image/.env` 与 `docker_lib/Ubuntu_image/.env` 当前属于仓库配置文件，不应写入生产密码。

## 兼容性与依赖

- Python 客户端依赖 `redis`，并通过其 ACL 用户名/密码参数认证。
- Redis 服务端需支持 ACL 用户配置。
- Redis 默认用户关闭后，旧版未认证客户端将无法连接；所有 Redis 客户端必须先完成环境变量迁移。

## 参考

- EventEngine 服务：[事件服务定义](./SDD-Event-Service.md)
- DataAgent 服务：[DataAgent 服务定义](./SDD-Data-Agent-Service.md)
- TimeAgent 服务：[TimeAgent 服务定义](./SDD-Time-Agent-Service.md)
