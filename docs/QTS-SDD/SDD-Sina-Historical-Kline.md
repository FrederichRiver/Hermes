# 新浪个股历史日K抓取与落库设计

## 概述

本文补充 WebsiteAgent 与 DataAgent 的既有设计，定义通过新浪财经抓取单只 A 股指定日期区间的日K线，并由 DataAgent 将结果幂等写入 `stock_daily`。抓取器只负责 HTTP 请求、响应校验和字段标准化；数据库连接、行校验与事务写入全部由 DataAgent 管理。

## 需求清单

1. WebsiteAgent 新增 `SiteSina` 站点适配器，支持任务类型 `historical_kline`，遵循 `BaseSite` / `HttpClient` 生命周期与 robots 校验流程。
2. 抓取任务必须提供 `symbol`、`start_date`、`end_date`。证券代码接受 `SH600000`、`SZ000001` 格式；日期接受 ISO `YYYY-MM-DD` 字符串或 `date` 值，起始日期不得晚于结束日期。
3. 请求新浪财经日K接口，返回区间内按交易日升序排列的 JSON 兼容行。标准行字段与 `StockDailyBar` 对齐：`symbol`、`trade_date`、`open`、`high`、`low`、`close`、`volume`、`amount`、`adj_factor`。
4. 按新浪接口单次最多返回 1023 根日K处理。若接口返回达到 1023 根且最早数据晚于请求起始日期，则抓取失败并明确报告区间无法完整覆盖；较短的响应按该证券当前可用历史数据处理。
5. WebsiteAgent 对 `historical_kline` 成功结果发布 `data.task.finished`，事件载荷包含 `task_id`、`task_type`、`rows_count`、`source="sina"` 和 `rows`。
6. DataAgent 消费上述完成事件，将记录交给 `stock_daily` 表操作对象做字段校验、日期及数值归一化，并在单个事务中按 `(symbol, trade_date)` 幂等 upsert。无效记录或数据库错误必须显式传播。
7. `stock_daily` 数据表按现有 `StockDailyBar` 模型存储；`adj_factor` 使用默认值 `1.0`，表示新浪本接口返回未复权 OHLC。

## 事件与接口

调用方通过 `data.fetch.requested` 请求指定证券和日期范围：

```python
Event.create(
    "data.fetch.requested",
    "scheduler",
    {
        "task": {
            "task_id": "sina-kline-sh600000-2024",
            "task_type": "historical_kline",
            "params": {
                "symbol": "SH600000",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            },
        },
    },
)
```

WebsiteAgent 路由到 `SiteSina`，抓取结果通过共享事件总线发送给 DataAgent。记录不携带额外名称字段；`symbol` 使用 `stock_index` 的交易所前缀格式。

## 职责边界与错误处理

- `SiteSina` 继承 `BaseSite`，使用其 `_http_clients` 中的 `HttpClient`，不连接数据库、不发布事件。
- WebsiteAgent 负责站点路由、robots 检查及 `data.task.finished` 结果事件发布。
- DataAgent 仅消费 `task_type="historical_kline"` 且 `source="sina"` 的完成事件；其他站点或任务不影响 `stock_daily`。
- `StockDailyBarEntity` 负责验证行字段及范围、把日期转为 `date`、将行情数值转为有限数值，并在一个数据库事务中按复合键新增或更新。
- 空响应、非 JSON 响应、缺字段、非法 OHLC、日期范围不完整及数据库写入失败均不得伪装成成功。
- 新浪单次最多 1023 根日K是本方案的接口边界。响应达到上限且无法覆盖请求起始日期时会失败，不承诺可用单次请求取得更早的完整历史；更早区间应由后续具备可靠分页能力的数据源或接口扩展支持。

## 兼容性与依赖

- Python 3.10+；继续使用现有 `requests`、`beautifulsoup4`、`PyMySQL` 与 EventEngine。
- 不改变现有 `symbol_list` / SSE 写入路径、`daily_bar` 事件语义或 `StockDailyBar` 字段定义。
- 数据库须预先存在 `stock_daily` 表，主键或唯一键为 `(symbol, trade_date)`。
- DataAgent 继续遵守 `MySQLMeta` 的 `SERVER_NAME` 数据库选择白名单策略。

## 参考

- [WebsiteAgent 设计](../WebsiteAgent/CDD-WebsiteAgent.md)
- [DataAgent 设计](../DataAgent/CDD-DataAgent.md)
- [DataEngine 设计](../DataEngine/CDD-DataEngine-v2.md)
