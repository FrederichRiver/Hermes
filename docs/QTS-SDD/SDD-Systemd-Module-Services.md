# Hermes 模块 systemd 服务管理定义

## 概述

本文定义 Hermes 常驻模块在 Linux 部署环境中的进程管理方式。`systemd` 负责服务启动、停止、重启和日志收集；Python 服务入口以前台方式运行，不自行 daemonize、不创建 PID 文件，也不执行进程监督。

模块职责、业务接口和事件协议保持独立。服务入口只负责连接依赖、初始化模块、处理停止信号和释放资源。

## 服务清单

| 服务单元 | 启动入口 | 职责 |
|---|---|---|
| `hermes-event.service` | `/opt/application/src/event_service.py` | 启动 EventEngine，并将启动事件写入 Redis Stream |
| `hermes-data.service` | `/opt/application/src/data_service.py` | 监听数据事件；处理股票列表刷新请求并写入 MySQL |
| `hermes-time-agent.service` | `/opt/application/src/time_agent_service.py` | 每分钟向 `time` Stream 发布带 60 秒有效期的时间点事件 |

服务单元文件位于仓库 `scripts/systemd/`。每个单元使用 `Type=simple`，由 systemd 直接跟踪 Python 进程；异常退出策略由 `Restart=on-failure` 控制。

## TimeAgent 时间点事件流程

1. TimeAgent 服务启动后等待 1 分钟，之后每隔 1 分钟产生 `time.cycle.timepoint` 事件。
2. 事件的 `event_data["timepoint"]` 为当前 UTC 时间的 ISO 8601 字符串。
3. 时间点事件写入名称为 `time` 的 Redis Stream，默认在产生后 60 秒过期并由 EventBus 清理。

抓取、数据校验和数据库事务由对应模块实现；systemd 不参与业务处理。

## 主入口约定

`src/main.py` 保留前台运行的命令行入口供开发或手动诊断使用，不再承担 daemonize、PID 文件管理、停止其他进程或清理本地日志文件的职责。部署环境中的服务启停应使用 systemd 单元，不应同时手动启动相同模块的第二个实例。

## 部署和运行环境

- 部署源码根目录：`/opt/application/src`。
- Python 解释器：`/opt/application/venv/bin/python3`。
- 服务单元中的 `ExecStart` 必须以前台方式运行对应入口。
- systemd 主机上必须实际存在上述源码和解释器路径。Docker 容器内没有 `systemctl` 时，应由宿主机的服务管理方案启动进程；不得在容器中假定 systemd 可用。
- `PYTHONPATH` 应包含源码根目录 `/opt/application/src`，其中直接包含 `basic_utils`、`event_engine`、`data_agent`、`time_agent` 和 `website_agent` 包。
- 服务收到 `SIGTERM` 或 `SIGINT` 后停止工作并关闭对应 Redis、Pub/Sub 和数据库资源。

## 环境变量和敏感信息

- Redis 客户端使用 `REDIS_URL`、`REDIS_USERNAME`、`REDIS_PASSWORD`；用户名和密码必须从部署环境注入。
- DataAgent 使用 `SERVER_NAME` 选择数据库，使用 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USERNAME`、`MYSQL_PASSWORD` 配置连接。Ubuntu Docker Compose 默认使用 `SERVER_NAME=Ubuntu_docker`、`MYSQL_HOST=172.18.0.2` 和 `MYSQL_PORT=3306`，可由部署环境覆盖。
- 邮件确认功能使用 `SMTP_*`、`IMAP_*` 环境变量；调用方应使用 `SmtpSettings.from_env()` 和 `ImapSettings.from_env()`。目前没有邮件服务入口自动加载这些设置。
- 生产凭据应保存在权限受限的环境文件或密钥管理系统中，不得写入源码、已跟踪的 `.env` 文件、systemd 单元或日志。
- Docker Compose 的变量插值需从宿主环境或显式指定的外部 `--env-file` 取得；容器 `env_file` 不会为 Compose 文件本身提供插值变量。
- Docker 环境变量生成脚本为 Ubuntu、Redis 和 Apache Compose 创建权限受限的 `.env.secrets`；启动 Ubuntu/Redis 时仍须使用 `docker compose --env-file .env.secrets`，修改环境后重建对应容器才能应用。

## 日志

服务入口使用共享的 `basic_utils.logging` 配置根 logger，将日志写入标准输出；systemd/journald 负责收集和查询日志。应用不创建本地日志文件或轮转文件。

## 验收要求

1. 每个服务单元都能直接以前台方式启动其对应入口，且不存在应用层 daemonize 或 PID 文件。
2. 服务可按单元独立启停；异常退出由 systemd 按单元策略恢复。
3. DataAgent 收到股票列表刷新事件后，调用 SSE 抓取器并将结果 upsert 到 `stock_index`。
4. Redis、MySQL 和邮件凭据均由环境配置提供，仓库中不包含生产秘密。
5. 服务日志可通过对应 systemd 单元在 journald 中查询。

## 参考

- [事件服务定义](./SDD-Event-Service.md)
- [DataAgent 服务定义](./SDD-Data-Agent-Service.md)
- [TimeAgent 服务定义](./SDD-Time-Agent-Service.md)
- [Redis 认证定义](./SDD-Redis-Authentication.md)
- [邮件凭据定义](./SDD-Email-Credentials.md)
