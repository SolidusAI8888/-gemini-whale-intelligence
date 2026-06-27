# V20 iCloud SMTP Mailer Hotfix

本版只修改邮件发送层，不改变 V19 的报告结构、扫描逻辑、Cabinet OGE 雷达和图表布局。

## 新增能力

- `EMAIL_PROVIDER=sendgrid`：继续使用 SendGrid。
- `EMAIL_PROVIDER=smtp`：使用 SMTP 发信，适合 iCloud Mail。
- iCloud 默认 SMTP 参数：
  - `SMTP_HOST=smtp.mail.me.com`
  - `SMTP_PORT=587`
  - `SMTP_STARTTLS=true`
- 支持多个收件人，用逗号或分号分隔 `EMAIL_TO`。
- `ENABLE_POLITICAL` 可作为 `ENABLE_POLITICAL_TRADES` 的别名，避免 GitHub Variables 命名混淆。

## iCloud Mail 推荐 GitHub Secrets

```text
EMAIL_PROVIDER=smtp
SMTP_USERNAME=你的 iCloud 邮箱，例如 yourname@icloud.com
SMTP_PASSWORD=Apple app-specific password
EMAIL_FROM=你的 iCloud 邮箱
EMAIL_TO=收件邮箱
```

`SMTP_PASSWORD` 不是 Apple ID 登录密码，而是 Apple Account 里生成的 app-specific password。

## GitHub Variables

```text
SEND_EMAIL=true
SMTP_HOST=smtp.mail.me.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_FROM_NAME=Gemini Whale Intelligence
```

如果已经确认不再使用 SendGrid，可以在 SMTP 测试成功后删除 `SENDGRID_API_KEY`。

## 覆盖文件

```text
app/reports/mailer.py
app/config.py
.github/workflows/daily_scan.yml
.env.example
tests/test_mailer.py
README_V20_ICLOUD_SMTP_MAILER.md
```
