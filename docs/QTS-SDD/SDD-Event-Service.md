# 事件总线 systemd 执行服务定义

## 概述

本文定义 `src/event_service.py` 作为事件引擎的常驻服务入口，供 Linux `systemd` 管理。服务复用 `event_engine` 中的 `EventEngine` 与 `RedisEventBus`，不改变事件引擎的模块职责、事件格式或业务处理逻辑。

服务以 systemd 前台进程模式运行：启动时连接 Redis、启动事件引擎并写入启动事件；运行期间等待停止信号；收到 `SIGTERM` 或 `SIGINT` 后停止引擎并关闭 Redis 连接。

## 需求

1. 使用仓库现有 `event_engine.EventEngine` 和 `event_engine.RedisEventBus`，不在服务入口复制事件总线实现。
2. 进程以前台方式运行，不执行 daemonize、不维护 PID 文件，也不自行重启。
3. Redis 连接地址通过 `REDIS_URL` 环境变量配置，默认值为 `redis://localhost:6379/0`；ACL 用户名和密码分别通过 `REDIS_USERNAME`、`REDIS_PASSWORD` 提供，不得硬编码在服务文件中。
4. 启动时检查 Redis 连通性，并将 `hermes.system.startup` 事件写入 `hermes:events` 流。
5. 收到 `SIGTERM` 或 `SIGINT` 时停止事件引擎并关闭 Redis 客户端；初始化或运行失败时记录异常并以非零状态退出，交由 systemd 按单元策略处理。
6. 日志输出到标准输出，由 systemd 日志服务收集。
7. 事件引擎源码直接部署在 `/opt/application/src/event_engine/`，不依赖安装 wheel 或执行 `pip install`。

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
- `RedisEventBus.subscribe()` 在监听器运行期间收到新事件类型时，必须将对应 Redis channel 加入订阅；订阅失败应撤销本次 handler 注册并显式向调用方报错。
- systemd 的重启策略、运行用户、权限和开机启用由部署单元配置负责。

## 参考

- 系统架构：[`../system-framework.md`](../system-framework.md)
- 事件引擎设计：[`../EventEngine/CDD-Event.md`](../EventEngine/CDD-Event.md)
- 实现入口：[`../../src/event_service.py`](../../src/event_service.py)
