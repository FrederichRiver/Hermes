# 邮件确认服务凭据配置定义

## 概述

本文定义邮件确认功能所需 SMTP（邮件发送协议）和 IMAP（邮件收取协议）用户名、密码的环境变量来源。业务对象不应在代码中保存或硬编码真实邮件凭据。

## 需求

1. `SmtpSettings.from_env()` 从 `SMTP_USERNAME`、`SMTP_PASSWORD` 读取 SMTP 登录凭据；主机、端口、发件人与收件人分别从 `SMTP_HOST`、`SMTP_PORT`、`SMTP_SENDER`、`SMTP_RECIPIENT` 读取。
2. `ImapSettings.from_env()` 从 `IMAP_USERNAME`、`IMAP_PASSWORD` 读取 IMAP 登录凭据；主机、端口、邮箱文件夹分别从 `IMAP_HOST`、`IMAP_PORT`、`IMAP_MAILBOX` 读取。
3. 必需环境变量缺失或为空时，应明确报错；不得使用硬编码凭据或静默空值。
4. SMTP 的 `SMTP_USE_STARTTLS` 可选，默认为启用。
5. 真实值由部署环境注入，不进入代码、版本控制或日志。

## 环境变量

```dotenv
SMTP_HOST=<SMTP 主机>
SMTP_PORT=587
SMTP_USERNAME=<SMTP 用户名>
SMTP_PASSWORD=<SMTP 密码>
SMTP_SENDER=<发件人地址>
SMTP_RECIPIENT=<收件人地址>
SMTP_USE_STARTTLS=true

IMAP_HOST=<IMAP 主机>
IMAP_PORT=993
IMAP_USERNAME=<IMAP 用户名>
IMAP_PASSWORD=<IMAP 密码>
IMAP_MAILBOX=INBOX
```

SMTP/IMAP 环境变量仅在启用邮件确认功能的服务中配置，并通过权限受限的环境文件提供。Ubuntu Docker Compose 服务支持向容器传入这些变量；未配置时保留为空值，邮件设置工厂在调用时会明确报错。
邮件确认调用方必须在创建 SMTP/IMAP 客户端前调用对应的 `from_env()`；当前尚无邮件服务入口自动加载这些环境设置。

## 兼容性与依赖

- 使用 Python 标准库 `os.environ` 读取配置，不增加第三方依赖。
- 直接构造 `SmtpSettings` / `ImapSettings` 的现有调用方式继续有效；`from_env()` 作为环境配置入口。

## 参考

- 邮件确认实现：[邮件确认模块](../../src/website_agent/src/website_agent/email_confirmation.py)
