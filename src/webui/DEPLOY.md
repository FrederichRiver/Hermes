# Hermes 量化交易系统 —— 部署指南

## 技术架构

| 层级 | 技术 |
|------|------|
| 前端 | 纯 HTML + CSS + JavaScript（Django 模板渲染） |
| 图表 | Chart.js (CDN) |
| 后端 | Django 5 + Django REST Framework |
| 数据库 | MySQL |
| 静态文件 | WhiteNoise |

---

## 目录结构

```
backend/
├── hermes/                 # Django 项目配置
│   ├── settings.py         # 数据库 / 静态文件 / DRF 配置
│   ├── urls.py             # 路由（API + 首页）
│   └── wsgi.py
├── apps/
│   └── core/               # 核心业务应用
│       ├── models.py       # 7 个数据模型
│       ├── serializers.py  # DRF 序列化器
│       ├── views.py        # API 视图
│       ├── urls.py         # API 路由
│       └── admin.py        # 后台管理
├── templates/
│   └── index.html          # 首页模板（完整 UI）
├── static/
│   ├── css/
│   │   └── hermes.css      # 深色金融主题样式
│   └── js/
│       └── hermes.js       # API 客户端 + 渲染逻辑
├── manage.py
├── seed_data.py            # 示例数据初始化
└── requirements.txt
```

---

## 快速启动

### 1. 环境准备

```bash
# 创建 Python 虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
cd backend
pip install -r requirements.txt
```

### 2. 数据库配置

确保 MySQL 已安装并运行，创建数据库：

```sql
CREATE DATABASE hermes_quant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'hermes_user'@'localhost' IDENTIFIED BY 'hermes_password';
GRANT ALL PRIVILEGES ON hermes_quant.* TO 'hermes_user'@'localhost';
FLUSH PRIVILEGES;
```

如需修改数据库配置，编辑 `backend/hermes/settings.py` 中的 `DATABASES`。

### 3. 数据库迁移

```bash
cd backend
python manage.py migrate
```

### 4. 创建管理员账户（可选）

```bash
python manage.py createsuperuser
```

### 5. 导入示例数据

```bash
cd backend
python manage.py shell < seed_data.py
```

### 6. 启动开发服务器

```bash
cd backend
python manage.py runserver
```

访问地址：
- **Dashboard 界面**：`http://127.0.0.1:8000/`
- **Django Admin**：`http://127.0.0.1:8000/admin/`
- **API 根地址**：`http://127.0.0.1:8000/api/v1/`

---

## 生产环境部署

### 收集静态文件

```bash
cd backend
python manage.py collectstatic --noinput
```

### 使用 Gunicorn 启动

```bash
gunicorn hermes.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### Nginx 反向代理示例

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location /static/ {
        alias /path/to/backend/staticfiles/;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## API 接口清单

| 端点 | 方法 | 说明 | 对应前端模块 |
|------|------|------|-------------|
| `/api/v1/dashboard/stats/` | GET | Dashboard 统计卡片 | 顶部 4 张卡片 |
| `/api/v1/positions/` | GET | 持仓列表 | 持仓表格 |
| `/api/v1/quotes/` | GET | 自选行情 | 行情面板 |
| `/api/v1/signals/?limit=20` | GET | 交易信号 | 信号日志 |
| `/api/v1/risk/` | GET | 风控指标 | 风控仪表盘 |
| `/api/v1/netvalue/` | GET | 净值曲线 | 净值图表 |
| `/api/v1/accounts/` | GET | 账户列表 | - |
| `/api/v1/logs/` | GET | 系统日志 | - |

---

## 前端技术说明

### 为什么不用 React / Node.js？

本系统前端采用**纯原生技术栈**，原因如下：

1. **零构建依赖**：无需 npm / webpack / vite，直接由 Django 模板渲染
2. **部署简单**：一个命令 `python manage.py runserver` 即可运行完整系统
3. **性能优秀**：原生 DOM 操作 + Chart.js，无虚拟 DOM 开销
4. **易于维护**：纯 HTML/CSS/JS，任何开发者都能直接阅读和修改
5. **与 Django 深度集成**：模板标签 `{% static %}` 自动处理静态文件路径

### 前端架构

| 文件 | 职责 |
|------|------|
| `templates/index.html` | 完整页面 DOM 结构 |
| `static/css/hermes.css` | 深色金融主题、布局、组件样式 |
| `static/js/hermes.js` | Fetch API 请求、数据渲染、Chart.js 初始化、定时刷新 |
| `Chart.js (CDN)` | 净值曲线图表 |

### 数据流

```
Django REST API → Fetch → JSON → JS 渲染 → DOM 更新
```

前端每 **30 秒** 自动刷新一次数据，保持界面与后端同步。

---

## 数据模型对照表

| Django Model | 前端模块 | 来源 Agent |
|-------------|---------|-----------|
| `Account` | Dashboard 统计 | TraderAccount |
| `Position` | 持仓表格 | TraderAccount / ExecutionEngine |
| `MarketQuote` | 自选行情 | DataAgent / MarketModel |
| `TradingSignal` | 信号日志 | StrategyAgent |
| `RiskMetric` | 风控监控 | RiskAgent |
| `NetValuePoint` | 净值曲线 | BacktestAgent |
| `SystemLog` | 日志中心 | EventEngine / Scheduler |

---

## 后续扩展建议

1. **WebSocket 实时推送**：接入 Django Channels，行情和信号秒级更新
2. **用户认证**：Django REST Framework TokenAuthentication / JWT
3. **Celery 定时任务**：数据爬虫定时执行、日终结算
4. **Redis 缓存**：行情数据缓存，降低数据库压力
5. **多账户支持**：前端添加账户切换下拉框
