# TimeAgent 源码服务定义

## 概述

本文定义 `time_agent` 模块采用与 `event_engine` 相同的源码目录布局，并新增 `time_agent_service.py` 供 systemd 以前台方式启动。

当前仓库中的 `TimeAgent` 实际接口与 `docs/TimeAgent/CDD-TimeAgent.md` 描述的完整计时运行器不同。服务实例化现有 `TimeAgent` 并记录当前状态；作为临时调度逻辑，启动后每隔 5 分钟通过 Redis 发布一个 `data.fetch.requested` SSE 股票列表任务，同时写入 `hermes:events` Stream。收到停止信号后正常退出，不调用 CDD 尚未实现的 `run()` / `stop()` 接口。

## 需求

1. Python 包源码直接位于仓库 `src/time_agent/`，部署后位于 `/opt/application/src/time_agent/`。
2. 服务入口位于 `/opt/application/src/time_agent_service.py`，进程以前台方式运行。
3. 服务创建当前实现的 `TimeAgent` 并记录 `status()`。
4. 服务启动后等待 5 分钟，再每隔 5 分钟发送 `data.fetch.requested` 事件；事件携带 `task.task_type="symbol_list"` 和空 `task.params`，由 DataAgent 启动 SSE 抓取并写入数据库。
5. 周期事件通过 Redis Pub/Sub 发布，同时将相同事件信封写入 `hermes:events` Stream。
6. Redis 地址、用户名和密码通过 `REDIS_URL`、`REDIS_USERNAME`、`REDIS_PASSWORD` 环境变量提供；用户名和密码必须设置，不得硬编码。
7. 收到 `SIGTERM` 或 `SIGINT` 后停止周期发送、关闭 Redis 客户端并以正常状态退出。
8. 日志输出到标准输出，由 `journald` 收集。

## 源码布局

```text
/opt/application/src/
├── time_agent_service.py
└── time_agent/
    ├── __init__.py
    ├── time_agent.py
    ├── time_core.py
    ├── time_engine.py
    └── time_event.py
```

模块导入名仍为 `time_agent.*`，但不再依赖在虚拟环境中安装项目分发包。

## systemd 服务示例

```ini
[Unit]
Description=Hermes TimeAgent service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/application
Environment=REDIS_URL=redis://172.18.0.7:6379/0
EnvironmentFile=/etc/hermes/redis.env
ExecStart=/opt/application/venv/bin/python3 /opt/application/src/time_agent_service.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## 兼容性与依赖

- Python 3.10+。
- 依赖直接部署的 `time_agent` 与 `event_engine` 源码及 Redis 客户端 `redis`。
- 5 分钟循环是服务层临时实现，不代表完整 CDD 计时功能已实现；后续接入 TimeCore/TimeEngine 时须先实现并验证对应接口，再更新本文及 `CDD-TimeAgent.md`。
- `REDIS_USERNAME` 与 `REDIS_PASSWORD` 应来自权限受限的 `/etc/hermes/redis.env`，不应以 `Environment=` 明文写入 systemd unit。

## 参考

- TimeAgent 设计：[`../TimeAgent/CDD-TimeAgent.md`](../TimeAgent/CDD-TimeAgent.md)
- TimeEvent 设计：[`../TimeAgent/CDD-TimeEvent.md`](../TimeAgent/CDD-TimeEvent.md)
- 事件服务定义：[`./SDD-Event-Service.md`](./SDD-Event-Service.md)
