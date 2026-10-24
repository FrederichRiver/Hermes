# TimeAgent 源码服务定义

## 概述

本文定义 `time_agent` 模块采用与 `event_engine` 相同的源码目录布局，并新增 `time_agent_service.py` 供 systemd 以前台方式启动。

当前仓库中的 `TimeAgent` 实际接口与 `docs/TimeAgent/CDD-TimeAgent.md` 描述的完整计时运行器不同。TimeAgent 持有 10 个独立线程计时器，每个计时器均可单独启动、停止并设置以秒为单位的运行间隔。服务启动 TimeAgent 后依次启动第一个计时器（间隔 60 秒）和第二个计时器（间隔 300 秒）；其余计时器保持停止，供后续配置。每个计时器首次等待完整间隔后，按周期发布 `time.timepoint.HHhMMm` 事件，例如 `time.timepoint.02h13m`；小时和分钟按 UTC 24 小时制、两位数格式生成。回调完成后再等待完整间隔，故回调执行耗时会累加到相邻事件的实际间隔。事件的 `event_data["timepoint"]` 保留当前 UTC 时间的 ISO 8601 字符串，事件在产生后 60 秒过期，并经 TimeAgent 的 `bus` 写入 `time` Redis Stream。收到停止信号后，服务停止所有计时器，再关闭 EventBus。

## 需求

1. Python 包源码直接位于仓库 `src/time_agent/`，部署后位于 `/opt/application/src/time_agent/`。
2. 服务入口位于 `/opt/application/src/time_agent_service.py`，进程以前台方式运行。
3. 服务创建当前实现的 `TimeAgent` 并记录 `status()`。
4. TimeAgent 创建 10 个独立计时器，初始均停止，且各自具有运行状态和以秒为单位的时间间隔；可通过方法动态设置间隔。
5. 服务启动第一个计时器，间隔为 60 秒；随后启动第二个计时器，间隔为 300 秒。其余计时器不自动启动。
6. 每个运行中的计时器先等待完整间隔，每次回调完成后再等待完整间隔；触发时发布 `time.timepoint.HHhMMm` 事件，时间后缀使用触发时的 UTC 小时和分钟（24 小时制、两位数）。
7. 事件的 `event_data["timepoint"]` 为 `str`，表示事件生成时的当前 UTC 时间点，格式为 ISO 8601。
8. 计时器事件产生后 60 秒过期；过期时由 EventBus 清理器从 `time` Stream 删除。计时器关闭时停止线程，并确保不再产生后续事件。
9. `TimeAgent` 实例持有与 `EventEngine` 一致的 `bus` 属性，引用同一类型的 EventBus；服务创建 `stream_name="time"` 的 EventBus 后注入 TimeAgent，由 TimeAgent 通过 Stream API 发布事件。
10. Redis 地址、用户名和密码通过 `REDIS_URL`、`REDIS_USERNAME`、`REDIS_PASSWORD` 环境变量提供；用户名和密码必须设置，不得硬编码。
11. 收到 `SIGTERM` 或 `SIGINT` 后停止所有计时器、关闭 Redis 客户端并以正常状态退出。
12. 日志输出到标准输出，由 `journald` 收集。
13. Redis 事件总线通过 `event_service.create_redis_event_bus()` 创建；服务入口通过总线执行 ping，并在服务停止时关闭其内部 Redis 客户端。

## 源码布局

```text
/opt/application/src/
├── time_agent_service.py
└── time_agent/
    ├── __init__.py
    ├── time_agent.py
    ├── time_timer.py
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
- 10 个线程计时器及当前两个服务间隔是服务层当前功能，不代表完整 CDD 计时功能已实现；后续接入 TimeCore/TimeEngine 时须先实现并验证对应接口，再更新本文及 `CDD-TimeAgent.md`。
- Event 默认过期时长为 60 秒；其他时长通过 `expires_in_seconds` 指定。过期清理由事件总线执行，Redis Stream 不支持单条记录 TTL，因此通过独立过期索引和后台清理实现。
- `REDIS_USERNAME` 与 `REDIS_PASSWORD` 应来自权限受限的 `/etc/hermes/redis.env`，不应以 `Environment=` 明文写入 systemd unit。

## 参考

- TimeAgent 设计：[`../TimeAgent/CDD-TimeAgent.md`](../TimeAgent/CDD-TimeAgent.md)
- TimeEvent 设计：[`../TimeAgent/CDD-TimeEvent.md`](../TimeAgent/CDD-TimeEvent.md)
- 事件服务定义：[`./SDD-Event-Service.md`](./SDD-Event-Service.md)
