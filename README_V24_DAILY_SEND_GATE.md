# V24 Daily Send Gate Hotfix

This hotfix changes only the scheduled delivery gate.

## Problem fixed

The previous workflow could skip the daily email if GitHub delayed or dropped the
06:17 UTC scheduled run. The 07:17 UTC fallback occurred at 09:17 Berlin in
summer and was rejected by the strict “Berlin 08 hour only” guard, so no email
was sent.

## New behavior

- Scheduled runs still fire at 06:17 and 07:17 UTC.
- Scheduled run is skipped before Berlin 08:00.
- The first scheduled run at or after Berlin 08:00 sends the report.
- A persisted `data/last_email_date.txt` marker prevents duplicate scheduled
  emails for the same Berlin calendar date.
- Manual `workflow_dispatch` always runs and does not mark the daily scheduled
  email as sent.

## Files changed

- `.github/workflows/daily_scan.yml`
- `README_V24_DAILY_SEND_GATE.md`
