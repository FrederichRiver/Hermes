# Hermes

Scheduler hot-reload: `src/event_engine/scheduler.py` uses Watchdog to reload `src/config/scheduler.json` on changes. Update job `func` values to point to module-level callables or add adapters.

A project of quantitive trading.

你可以将以下内容保存�?docs/README.md �?docs/DOC_GUIDE.md，作为你的文档组织和维护指南�?

---

# Hermes 项目文档组织与维护指�?

## 目录结构建议

```
docs/
├── README.md                # 文档总览与导�?
├── src-SDD/                 # 系统设计说明书（详细设计、架构、流程）
�?  ├── src-SDD-v0.1.md
�?  └── src-SDD-v0.2.md
├── AGENTS.md                # Agent/模块设计与接口说�?
├── API.md                   # Web/API接口文档
├── DB_SCHEMA.md             # 数据库结构与表说�?
├── UI_DESIGN.md             # 用户界面与交互设�?
├── WORKFLOW.md              # 关键业务流程与用�?
└── CHANGELOG.md             # 设计和实现变更记�?
```

## 各文档说�?

- **README.md**：简要介绍文档体系、各文档作用和入口导航�?
- **src-SDD/**：系统设计说明书，详细描述架构、模块、数据流、技术选型等�?
- **AGENTS.md**：专门记录各Agent/模块的功能、接口、协作方式�?
- **API.md**：Web服务、前后端、第三方接口的输入输出格式、协议说明�?
- **DB_SCHEMA.md**：数据库表结构、字段说明、索引、关系等�?
- **UI_DESIGN.md**：界面原型、页面结构、交互流程、主要字段�?
- **WORKFLOW.md**：典型业务流程、用例、时序图等�?
- **CHANGELOG.md**：每次设�?实现变更的简要记录，便于追溯�?

## 维护建议

- 每次设计或实现有重大调整时，及时同步更新相关文档�?
- 文档内容建议使用Markdown格式，便于版本管理和协作�?
- 目录结构和命名保持简洁、统一，便于长期维护�?
- 重要决策、约束、TODO等可用专门小节或标签标注�?

---

本指南用于规范Hermes项目的文档编写、归档和维护，确保系统设计与实现过程的可追溯性和高效协作�
