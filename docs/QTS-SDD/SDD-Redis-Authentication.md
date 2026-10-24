# Redis 认证配置定义

## 概述

本文定义 Hermes 服务访问 Redis 时的 ACL（访问控制列表）认证配置。Redis 用户名与密码通过运行环境注入，客户端和 Redis 服务端使用相同配置；凭据不得提交到源码或镜像配置文件。

## 需求

1. 客户端使用 `REDIS_URL` 指定 Redis 地址，使用 `REDIS_USERNAME`、`REDIS_PASSWORD` 分别提供 ACL 用户名和密码。
2. Redis 连接与 `RedisEventBus` 统一由 `event_service.create_redis_event_bus()` 创建，Event、Data、TimeAgent 和 WebsiteAgent 服务入口复用该方法。
3. Redis 服务容器从环境变量生成 ACL 配置，不在 `redis.conf` 或镜像层保存密码明文。
4. Redis `default` 用户关闭，只启用配置的 ACL 用户。
5. ACL 用户仅能访问 `event:*` Pub/Sub 频道；该权限必须覆盖 `RedisEventBus` 发布和订阅的 `event:<event_type>`。
6. Redis 配置必须加载启动脚本生成的 ACL 文件；启动脚本未能生成或加载 ACL 时，服务应启动失败，不得回退到未认证模式。
7. Compose 在缺少用户名或密码时应明确失败；不得悄悄以未认证方式连接。
8. Ubuntu 应用容器和 Redis 容器从受保护的环境配置中取得同一组 Redis 凭据。
9. 迁移覆盖所有仍在使用的源码 Redis 客户端，包括 Event、Data、TimeAgent 和 WebsiteAgent 服务入口。

## Redis 事件总线工厂

`src/event_service.py` 在 `main()` 外定义 `create_redis_event_bus()`，读取 Redis 环境配置、创建底层 redis-py 客户端，并用该客户端构造 `RedisEventBus`。方法只返回事件总线；Redis 客户端作为其内部成员由总线持有：

```python
event_bus = create_redis_event_bus()
event_bus.ping()
```

- 可选参数 `url` 不为 `None` 时直接作为连接地址；未提供时依次读取 `REDIS_URL` 和 `default_url`。
- `default_url` 默认是 `redis://localhost:6379/0`；SSE spider 可传入容器网络默认地址 `redis://redis:6379/0`。
- `REDIS_USERNAME` 与 `REDIS_PASSWORD` 必须由环境提供；缺少任一变量时明确抛出异常。
- 客户端使用 5 秒连接超时和 5 秒套接字超时，默认不解码响应，保持 Redis 协议原始字节行为。
- `RedisEventBus` 提供 `ping()`、Stream 操作和 `close()`；`close()` 停止 Pub/Sub 监听器并关闭内部 Redis 客户端。底层 Redis 异常直接传播。
- `basic_utils` 不再定义或导出 Redis 客户端包装对象。

## 环境变量

```dotenv
REDIS_USERNAME=fred
REDIS_PASSWORD=<由部署环境提供的强随机密码>
REDIS_URL=redis://172.18.0.7:6379/0
```

生产环境应将这些变量保存在权限受限的环境文件或容器密钥管理机制中，不将真实密码写入仓库。Redis 客户端和服务器必须使用相同用户名、密码。Docker Compose 可用 `--env-file /etc/hermes/redis.env` 为服务端与客户端注入同一组变量；`docker_lib/Redis_image/.env` 与 `docker_lib/Ubuntu_image/.env` 当前属于仓库配置文件，不应写入生产密码。

## Redis ACL 配置

Redis 启动脚本在运行时生成唯一 ACL 用户，密码以 SHA-256 哈希形式写入 `/run/redis-users.acl`。Redis 配置关闭 `default` 用户并加载该 ACL 文件。用户拥有应用所需的 Redis 命令和 key 权限，同时通过 `&event:*` 明确允许 Hermes 事件频道。缺少该频道规则时，Pub/Sub 订阅可能在读取订阅响应时返回 `NoPermissionError`，导致 Redis 事件监听线程退出。

## 兼容性与依赖

- Python 客户端依赖 `redis`，并通过其 ACL 用户名/密码参数认证。
- Redis 服务端需支持 ACL 用户配置。
- Redis 默认用户关闭后，旧版未认证客户端将无法连接；所有 Redis 客户端必须先完成环境变量迁移。

## 参考

- EventEngine 服务：[事件服务定义](./SDD-Event-Service.md)
- DataAgent 服务：[DataAgent 服务定义](./SDD-Data-Agent-Service.md)
- TimeAgent 服务：[TimeAgent 服务定义](./SDD-Time-Agent-Service.md)
- Redis 事件总线工厂：[`../../src/event_service.py`](../../src/event_service.py)
- Redis 服务端配置：[`../../docker_lib/Redis_image/`](../../docker_lib/Redis_image/)
