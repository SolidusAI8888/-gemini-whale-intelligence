# V28 - Auto Email Backup + Report Grouping Hotfix

## 目标

本版解决两个问题：

1. 自动 scheduled run 已经执行完整扫描但用户仍未收到邮件。
2. 报告首页新增内容总览与 13F 展示方式需要更适合快速阅读。

## 自动邮件修复

V28 保留 V26/V27 的应用内发送逻辑，并新增一个 workflow 级别的 scheduled-only 备用 SMTP 发送步骤：

- `app/main.py` 在 `send_report(...)` 成功后写入 `data/email_sent.flag`。
- scheduled run 完成扫描后，如果没有发现 `data/email_sent.flag`，workflow 会直接用 SMTP 读取最新 HTML 报告并补发。
- manual run 不执行备用补发，避免手动测试重复邮件。
- 如果备用 SMTP 也失败，workflow 会失败，不会写入 `last_email_date.txt`。

这样 scheduled run 不再只依赖 Python 应用内部的邮件开关；即使应用层没有发出，workflow 也会补发一次。

## 报告展示修复

### 今日新增内容总览

- 相对上一轮成功运行的新内容仍为整行橙色高亮。
- 同一个类别下的同一个标的合并成一行。
- 巨鲸/机构名字并列展示。
- 按合计金额降序排列。

### 13F 机构巨鲸雷达

- 13F 金额增加单位保护：如果单个持仓因 XML 单位差异被放大成不合理的万亿美元级别，会自动规范化。
- 13F 表格展示时，同一个机构的持仓连续集中展示。
- 机构组按该机构最大持仓市值排序；组内按持仓市值降序排序。

## 覆盖文件

- `.github/workflows/daily_scan.yml`
- `app/main.py`
- `app/collectors/sec_13f.py`
- `app/reports/html_report.py`

## 测试

```bash
pytest -q
```

本地测试：`19 passed`。
