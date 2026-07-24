# V39.1 Stage 1 — WIS Core Scoring Integrity

This incremental patch contains the first V39.1 milestone:

- missing source scores remain `None` / `N/A` rather than defaulting to 50;
- dynamic weight normalization uses only available components;
- coverage, confidence, signal count and freshness are emitted on `WISScore`;
- an independent downside-risk calculation is introduced;
- regression tests cover the new behavior.

## Files

- `app/intelligence/models.py`
- `app/intelligence/score_engine.py`
- `tests/test_wis_v39_1.py`

## Verification

The complete V39.1 working tree passed:

```text
37 passed
```

This is an incremental review package, not the final V39.1 release.
