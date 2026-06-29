# V23 Baseline-aware Daily Diff Hotfix

This hotfix clarifies daily change detection. If no prior `data/whale.db` is restored, the report now says it is establishing a baseline instead of labeling all collected historical rows as today's new changes. If a baseline is restored, the report shows the baseline row count and only new inserts as daily changes.

Files changed:
- `app/main.py`
- `app/reports/html_report.py`
- `.github/workflows/daily_scan.yml`
