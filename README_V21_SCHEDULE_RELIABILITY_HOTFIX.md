# V21 Schedule Reliability Hotfix

本补丁只修复 GitHub Actions 定时触发时间，不改变 V20/V19 的报告内容、iCloud SMTP 邮件发送、Cabinet OGE、图表和扫描逻辑。

## 背景

用户发现 Scheduled workflow 在柏林时间下午 13:16 / 14:00 / 14:10 附近触发，只运行 7-8 秒就结束，说明 workflow 被“柏林 08:00 时间窗”判断跳过，没有执行扫描和发邮件。

## 修复内容

### 1. 避开 GitHub Actions 整点高峰

旧 cron：

```yaml
- cron: '0 6 * * *'
- cron: '0 7 * * *'
```

新 cron：

```yaml
- cron: '17 6 * * *'
- cron: '17 7 * * *'
```

含义：

- 德国夏令时 CEST：`06:17 UTC = Berlin 08:17`
- 德国冬令时 CET：`07:17 UTC = Berlin 08:17`

这样既保持“柏林早上 8 点档”发送，又避开 GitHub 定时任务整点拥堵。

### 2. 更清晰的时间诊断日志

workflow 现在会打印：

```text
current_utc=...
current_berlin=...
berlin_hour=... berlin_minute=...
should_run_daily_email=true/false reason=...
```

如果被跳过，会明确写出：

```text
Skipping scheduled run because Berlin local time is ..., not during the 08:00 hour.
```

### 3. 手动触发不受限制

`workflow_dispatch` 仍然直接执行，不受柏林 08:00 判断限制。

## 覆盖文件

```text
.github/workflows/daily_scan.yml
README_V21_SCHEDULE_RELIABILITY_HOTFIX.md
```

## 预期结果

每天会有两个 scheduled run：

- 一个在柏林 08:17 左右真正执行扫描和邮件发送
- 另一个因不是 Berlin 08 点小时而跳过

夏令时和冬令时自动适配，不需要手动调整。
