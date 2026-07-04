# V31 — Pre-armed Berlin 08:00 Delivery

## Root cause

GitHub `schedule` events are best-effort. A cron expression does not guarantee a workflow run will be created exactly at the target time. In the observed runs, scheduled workflows were created later in the day, while the Berlin 08:00 window had no run at all. That means the email system and scanner can be healthy while there is simply no morning workflow instance to send the report.

## Fix

V31 stops relying on a cron event being created exactly at 08:00. Instead, scheduled workflows are pre-armed before 08:00 Berlin time and the runner sleeps until the target time before scanning and sending.

Schedule:

```yaml
- cron: '13,43 3-7 * * *'
- cron: '13 10 * * *'
```

The first line creates several pre-08:00 attempts covering both CET and CEST. Job-level concurrency queues attempts so only one can run at a time. The first successful job waits until Berlin 08:00, scans, and sends. Later queued jobs restore the daily marker and skip.

The second line is a same-day fallback: normally it skips; if GitHub drops all morning triggers, it sends late instead of missing the day entirely.

## Important limitation

This is the strongest fix possible while relying only on GitHub-hosted scheduled workflows. GitHub still does not provide an SLA that any scheduled event will be created. For mission-critical exact 08:00 delivery, use an external scheduler such as cron-job.org, EasyCron, a VPS cron, NAS, or a local Mac launchd job to call GitHub `workflow_dispatch` at Berlin 08:00.

## Changed file

- `.github/workflows/daily_scan.yml`
