# DataAgent 源码服务定义

## 概述

本文定义将原 `data_engine` 模块更名为 `data_agent`，并采用与 `event_engine` 相同的源码目录布局。`data_service.py` 作为 systemd 前台服务入口，创建 Redis 事件总线及 `DataAgent`，接收周期抓取请求、调用 SSE 抓取器，并将股票列表写入 MySQL。DataAgent 也消费新浪财经历史日K完成事件，将经验证的日线记录写入 `stock_daily`。

本次调整变更模块包名、源码路径和进程托管方式，并增加周期股票列表抓取请求的消费流程；现有完成事件处理、数据库表操作及数据校验逻辑继续保留。

## 需求

1. Python 包名由 `data_engine` 改为 `data_agent`，源码直接位于仓库 `src/data_agent/`，部署后位于 `/opt/application/src/data_agent/`。
2. 服务入口位于 `/opt/application/src/data_service.py`，以前台方式运行，由 systemd 控制生命周期。
3. 服务通过 `REDIS_URL`、`REDIS_USERNAME` 和 `REDIS_PASSWORD` 连接 Redis；地址缺省为 `redis://localhost:6379/0`，用户名和密码必须由环境提供。
4. DataAgent 订阅 `data.fetch.requested`。当请求任务类型为 `symbol_list` 时，直接调用 WebsiteAgent 的 `SiteSSE.fetch_stock_code()`，然后复用 `stock_index` 表操作对象进行校验、归一化和事务性 upsert。
5. DataAgent 保留对 `data.task.finished` 的兼容订阅，用于接收已有 WebsiteAgent 完成事件。
6. DataAgent 消费 `task_type="historical_kline"` 且 `source="sina"` 的 `data.task.finished` 事件，将 `rows` 委托给 `stock_daily` 表操作对象，在单个事务中按 `(symbol, trade_date)` 幂等写入。
7. `stock_daily` 表使用 `StockDailyBar` 字段，并以 `(symbol, trade_date)` 为主键或唯一键；表须由部署/数据库初始化流程预先创建。
8. 服务使用现有 `SERVER_NAME` 白名单策略选择数据库，生产机名称须以 `Ubuntu_` 开头；主机、端口、用户名和密码可由 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_USERNAME`、`MYSQL_PASSWORD` 配置，用户名缺省为 `stock`，密码缺省为空。
9. 服务停止时关闭 Redis Pub/Sub 监听器、DataAgent 管理的数据库连接及 Redis 客户端；初始化或运行异常必须写入日志并以非零状态退出。
10. 服务日志写入标准输出，由 `journald` 收集。
11. 不要求部署时安装 `hermes-data-engine` 或 `hermes-data-agent` 分发包；依赖库须已存在于服务使用的 Python 虚拟环境。

## 源码布局

部署目录遵循以下结构，应用源码根目录即 Python 模块搜索路径：

```text
/opt/application/src/
├── data_service.py
├── data_agent/
│   ├── __init__.py
│   ├── data_agent.py
│   ├── mysql_meta.py
│   ├── mysql_table.py
│   ├── models.py
│   └── stock_tables.py
├── event_engine/
    └── ...
└── website_agent/
    └── src/
        └── website_agent/
            └── ...
```

项目内引用统一使用 `data_agent.*`，不保留 `data_engine` 兼容导入路径。

## systemd 服务示例

服务单元以前台方式启动，不使用 daemonize、PID 文件或应用内自动重启。

```ini
[Unit]
Description=Hermes DataAgent service
After=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/application
EnvironmentFile=/etc/hermes/data-service.env
ExecStart=/opt/application/venv/bin/python3 /opt/application/src/data_service.py
Restart=on-failure
RestartSec=5
KillSignal=SIGTERM
TimeoutStopSec=30
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

运行配置可通过受限权限的 `/etc/hermes/data-service.env` 提供，例如 `SERVER_NAME=Ubuntu_production`、`MYSQL_HOST=172.18.0.2`、`MYSQL_PORT=3306`、`MYSQL_USERNAME=stock`、`MYSQL_PASSWORD`、`REDIS_URL=redis://172.18.0.7:6379/0`、`REDIS_USERNAME` 和 `REDIS_PASSWORD`。Ubuntu Docker Compose 的默认值使用 `SERVER_NAME=Ubuntu_docker` 和 `MYSQL_HOST=172.18.0.2`；这些值可由部署环境覆盖。`SERVER_NAME` 仍负责选择数据库名；连接用户名和密码由环境变量提供。

## 兼容性与依赖

- Python 3.10+。
- `event_engine`、`website_agent` 源码与 Redis 客户端 `redis`。
- MySQL 驱动 `PyMySQL`。
- `SERVER_NAME` 必须符合 `resolve_stock_connection` 现有白名单；默认数据库用户为 `stock`，密码为空，可使用 `MYSQL_USERNAME`、`MYSQL_PASSWORD` 覆盖。
- 服务订阅 `data.fetch.requested` 并处理 `symbol_list` 任务；DataAgent 同时兼容消费 SSE 完成事件与新浪历史日K完成事件。

## 参考

- 数据代理设计：[`../DataAgent/CDD-DataAgent.md`](../DataAgent/CDD-DataAgent.md)
- 数据引擎设计约束：[`../DataEngine/`](../DataEngine/)
- 新浪历史日K抓取与落库：[`./SDD-Sina-Historical-Kline.md`](./SDD-Sina-Historical-Kline.md)
- 事件服务定义：[`./SDD-Event-Service.md`](./SDD-Event-Service.md)
