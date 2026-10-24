# 事件总线 systemd 执行服务定义

## 概述

本文定义 `src/event_service.py` 作为事件引擎的常驻服务入口，供 Linux `systemd` 管理。服务复用 `event_engine` 中的 `EventEngine` 与 `RedisEventBus`，不改变事件引擎的模块职责、事件格式或业务处理逻辑。

服务以 systemd 前台进程模式运行：启动时连接 Redis、启动事件引擎并写入启动事件；运行期间等待停止信号；收到 `SIGTERM` 或 `SIGINT` 后停止引擎并关闭 Redis 连接。

`event_service.py` 在 `main()` 外定义 `create_redis_event_bus()`，集中创建 Redis 客户端和 `RedisEventBus`。工厂只返回 `RedisEventBus`，底层客户端由其内部持有；调用方通过事件总线的 `ping()`、`xadd()` 和 `close()` 等接口操作 Redis。该工厂供 Event、Data、TimeAgent 和 WebsiteAgent 服务入口复用，不额外设置 `basic_utils` Redis 客户端封装。

## 需求

1. 使用仓库现有 `event_engine.EventEngine` 和 `event_engine.RedisEventBus`，不在服务入口复制事件总线实现。
2. 进程以前台方式运行，不执行 daemonize、不维护 PID 文件，也不自行重启。
3. Redis 连接地址通过 `REDIS_URL` 环境变量配置，默认值为 `redis://localhost:6379/0`；ACL 用户名和密码分别通过 `REDIS_USERNAME`、`REDIS_PASSWORD` 提供，不得硬编码在服务文件中。
4. 启动时检查 Redis 连通性，并将 `hermes.system.startup` 事件写入本模块的 `event` 流。
5. 收到 `SIGTERM` 或 `SIGINT` 时停止事件引擎并关闭 Redis 客户端；初始化或运行失败时记录异常并以非零状态退出，交由 systemd 按单元策略处理。
6. 日志输出到标准输出，由 systemd 日志服务收集。
7. 事件引擎源码直接部署在 `/opt/application/src/event_engine/`，不依赖安装 wheel 或执行 `pip install`。
8. `src/event_service.py` 在 `main()` 外提供 `create_redis_event_bus()`，统一创建经 ACL 认证的 Redis 客户端和 `RedisEventBus`，且只返回事件总线；Event、Data、TimeAgent 服务入口复用此工厂，通过事件总线执行 ping、Stream 操作和资源释放。

## 源码目录结构

事件引擎采用可直接导入的源码布局，`event_service.py` 所在目录同时作为 Python 模块搜索路径：

```text
/opt/application/src/
├── event_service.py
└── event_engine/
    ├── __init__.py
    ├── event.py
    ├── event_bus.py
    ├── event_engine.py
    └── ...
```

目录中保留 `event_engine` 包名及其模块接口；`src/event_engine/src/event_engine/` 不再作为正式源码位置，避免部署时增加额外的 `PYTHONPATH` 配置。

## 运行接口

部署后使用应用虚拟环境运行入口：

```ini
[Service]
Type=simple
WorkingDirectory=/opt/application
EnvironmentFile=/etc/hermes/event-service.env
ExecStart=/opt/application/venv/bin/python /opt/application/src/event_service.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal
```

`/etc/hermes/event-service.env` 可设置 Redis 连接地址和凭据，例如 `REDIS_URL=redis://172.18.0.7:6379/0`、`REDIS_USERNAME` 和 `REDIS_PASSWORD`。生产凭据应通过权限受限的配置文件或部署环境注入。

## 兼容性与边界

- 依赖 Python 3.10+、直接部署的 `event_engine` 源码和运行环境中的 `redis`、`APScheduler` 依赖。
- 服务从 `/opt/application/src` 运行，使 `event_engine` 可直接导入；不得依赖 `event_engine` 已安装到虚拟环境。
- 服务只负责事件引擎进程生命周期，不在此入口注册业务订阅者；事件生产者和消费者仍按现有方式使用 Redis 总线。
- `create_redis_event_bus()` 可由其他服务入口导入；该方法只返回 `RedisEventBus`，不自行 ping，底层客户端由事件总线持有。事件总线提供 `ping()` 和 `close()`，调用方负责调用并管理资源生命周期。
- 旧式 `RedisEventBus.subscribe()` 仅为兼容保留且不推荐；新事件流程使用 Redis Stream 和模块注册表。
- systemd 的重启策略、运行用户、权限和开机启用由部署单元配置负责。

## EventBus Stream 与动态注册

`RedisEventBus` 创建时通过 `stream_name` 指定 Stream 名称。各模块使用各自的 Stream：EventEngine 使用 `event`，DataAgent 使用 `data`，TimeAgent 使用 `time`，WebsiteAgent 使用 `REDIS_STREAM_NAME` 配置的名称（默认 `market:listings:sse`）。未显式传入名称时保留 `ChannelA` 作为兼容默认值。事件发布和消费均绑定到该实例的 Stream；低层 `xadd(stream_name, fields)` 仍可显式指定目标 Stream。

每个事件在创建时默认设置 60 秒过期时间，也可通过 `expires_in_seconds` 按事件配置非负整数秒数（0 表示立即过期）。信封中的 `expires_at` 是 UTC Unix 毫秒时间戳。RedisEventBus 将待过期条目登记到该 Stream 对应的有序索引，并将 Stream 名称记入全局索引；后台清理器每秒检查一次，据此删除已到期条目，并清除相关消费者组的待确认记录。创建 Stream 条目、登记有序索引和全局索引必须作为一个原子操作完成；实际删除时间为过期时刻加上最多一个轮询间隔及本轮清理耗时。过期是 Stream 级别的全局行为：到期后所有消费者组均不再获得该事件。没有 `expires_at` 的历史信封仍可读取，且不受自动清理。

事件总线关闭时停止过期清理器。清理器清理失败时记录错误并重试，不得静默丢弃事件或过期索引。

模块消费时需提供本模块的 UTF-8 JSON 注册文件，默认每 60 秒重新读取。JSON 对象以事件类型为键、代码中已声明的处理函数键为值：

```json
{
  "data.stock_list.fetched": "save_stock_list",
  "time.market.open": "on_market_open"
}
```

处理函数由模块代码通过 `register_handler(handler_key, function)` 显式登记。JSON 只绑定事件类型与处理函数键，不得动态导入或执行文件中的代码。成功读取后整体替换内存注册表；文件缺失、JSON 格式非法或事件类型无效时记录错误日志，并保留上一次有效注册表。

消费到已注册事件时调用对应函数；若注册表引用的函数未在代码中声明，记录错误日志并确认该消息。未登记的事件类型直接确认，不调用模块函数。处理函数执行失败时记录异常且不确认消息，以保留待重试状态。无法解析的事件信封写入 `<stream_name>:dead-letter` 后确认原消息；死信写入失败时保留原消息。

```python
bus = RedisEventBus(
    redis_client,
    stream_name="data",
    consumer_group="data-agent",
    registration_file="config/data-agent-events.json",
    poll_interval=60,
)
bus.register_handler("save_stock_list", save_stock_list)
bus.start()
```

`publish_stream(event)` 将事件信封写入实例配置的 Stream；旧式 Pub/Sub `publish()` / `subscribe()` 和 Redis List `enqueue()` 仅兼容保留，均不推荐用于新流程。

## 参考

- 系统架构：[`../system-framework.md`](../system-framework.md)
- 事件引擎设计：[`../EventEngine/CDD-Event.md`](../EventEngine/CDD-Event.md)
- 实现入口：[`../../src/event_service.py`](../../src/event_service.py)
