# V26 Scheduled Email Force Fix

This hotfix makes scheduled and manual runs use the same final email-send decision.

## Problem addressed

Manual `workflow_dispatch` runs were able to scan and send email successfully, while `schedule` runs completed a full 18–20 minute scan but no email was received. That means SMTP credentials and iCloud Mail were valid, and the failure was in the scheduled-run email gate / environment resolution.

## What changed

1. Once the Berlin daily gate decides a run should execute, the workflow sets:

```yaml
FORCE_SEND_EMAIL: 'true'
SEND_EMAIL: 'true'
```

on the actual `python -m app.main` step.

2. `app/config.py` now treats `FORCE_SEND_EMAIL=true` as an override:

```python
send_email = FORCE_SEND_EMAIL or SEND_EMAIL
```

3. The workflow prints safe diagnostics before the scan:

- event name
- Berlin gate outputs
- configured provider
- whether EMAIL_TO and SMTP_USERNAME are present
- final forced email setting

Secrets are not printed.

## Expected behavior

- Manual run: scan + send email.
- Scheduled run before Berlin 08:00: skip.
- First eligible scheduled run on a Berlin date: scan + send email, even if there are zero new disclosures.
- Later scheduled runs on the same Berlin date: skip after `data/last_email_date.txt` is restored.

## Files changed

- `.github/workflows/daily_scan.yml`
- `app/config.py`
- `README_V26_SCHEDULED_EMAIL_FORCE_FIX.md`
