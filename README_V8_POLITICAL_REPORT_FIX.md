# V8 Political Report Display Fix

This hotfix fixes the case where POLITICAL_HOUSE records are collected and inserted into SQLite but do not appear in the report.

## Changed files

- `app/db.py`
  - adds `fetch_recent_political_trades()`
  - adds `fetch_political_action_summary()`
- `app/main.py`
  - fetches political trades separately from generic recent trades
  - merges political trades into the report rows so SEC Form 4 rows cannot crowd them out
  - passes political diagnostic summary into the report
- `app/reports/html_report.py`
  - robust political detection: `source.startswith('POLITICAL')` OR `whale_category.startswith('Political')`
  - displays `POLITICAL_HOUSE` BUY/SELL rows
  - adds “政界交易诊断汇总” table

## Why this was needed

Your Actions log showed:

- `Political House official diagnostics: ... trades=111`
- `Political trades collected after de-duplication: 111; scope=all`

But the HTML report still showed no political trades. The generic recent-trades query was dominated by recent SEC Form 4 rows and the report filter was too narrow.

## Upload instructions

Upload/overwrite these files in your GitHub repository:

```text
app/db.py
app/main.py
app/reports/html_report.py
README_V8_POLITICAL_REPORT_FIX.md
```

Then run GitHub Actions again.
