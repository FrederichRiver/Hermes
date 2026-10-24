# 应用日志配置定义

## 概述

本文定义 Hermes Python 模块的统一日志配置。服务由 systemd 前台托管时，应用日志写入标准输出，由 journald 收集；应用代码不再管理本地日志文件、轮转文件或文件监视器。各模块通过共享的 `basic_utils.logging` 获取以模块名标识的标准 Python logger，并直接调用其日志方法。

## 需求

1. 统一实现位于 `basic_utils.logging`，源文件名为 `logging.py`；不保留 `logging_config.py` 导入路径。
2. `configure_logging()` 配置根 logger，将日志写入标准输出，使用一致的时间、级别、模块名和消息格式。
3. 日志级别可通过 `LOG_LEVEL` 环境变量配置，缺省为 `INFO`。
4. `get_logger(module_name)` 返回使用给定模块名的标准 logger；空模块名应明确报错。
5. 日志调用方直接调用 `logger.debug()`、`logger.info()`、`logger.warning()`、`logger.error()` 或 `logger.exception()`；不再经由专用 `log_error()` 包装函数。
6. 初始化应具备幂等性，重复配置不可累加重复的标准输出处理器。
7. 不创建应用日志文件或轮转文件；systemd 管理服务时由 journald 管理日志收集与保留。
8. 配置模块不改变业务逻辑，只统一日志初始化、日志输出目标和模块标识。

## 接口

```python
from basic_utils.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
logger.info("Service started.")
```

`configure_logging()` 在进程入口初始化一次根 logger。`get_logger()` 使用模块名获取 logger，不负责改变业务行为；`logger` 直接输出到共享的标准输出处理器。

`basic_utils` 包根统一导出可复用的 HTTP 客户端、日志函数和公开解析函数，同时保留 `http_client`、`logging`、`parser` 子模块入口；私有辅助函数不作为包级接口。

## 兼容性与依赖

- 使用 Python 标准库 `logging`，不增加第三方依赖。
- 源码文件位于 `src/basic_utils/logging.py`；部署时将 `/opt/application/src` 作为 Python 模块搜索路径，以导入 `basic_utils.logging`。
- 适用于由 systemd 管理并将标准输出接入 journald 的服务。
- 迁移后不承诺本地 `hermes.log` 文件及其轮转行为；需要查询服务日志时使用 `journalctl`。

## 参考

- 系统架构：[系统架构](../system-framework.md)
- EventEngine 服务定义：[事件服务定义](./SDD-Event-Service.md)
- DataAgent 服务定义：[DataAgent 服务定义](./SDD-Data-Agent-Service.md)
- TimeAgent 服务定义：[TimeAgent 服务定义](./SDD-Time-Agent-Service.md)
