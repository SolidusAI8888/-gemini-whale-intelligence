# V29 Morning Cron + 13F Amount Repair

## What changed

1. Scheduled runs now use dense morning attempts around the Berlin 08:00 target:
   - `7,22,37,52 5-10 * * *`
   - `17 11-18 * * *`

   The existing Berlin daily gate still sends at most one scheduled email per Berlin date.
   Extra short scheduled runs after a successful email are expected.

2. Existing persisted `INSTITUTIONAL_13F` rows with impossible values above $500B are repaired in-place by dividing by 1000.
   This fixes V27/V28 rows that remained in the cached SQLite database because inserts use stable `source_id` keys.

## Expected workflow behavior

- Manual runs still always scan and send.
- Scheduled runs repeatedly try after Berlin 08:00.
- The first successful scheduled run for the Berlin date sends the daily report.
- Later scheduled attempts skip in a few seconds after seeing `data/last_email_date.txt`.
