# V39.1 — Signal Integrity & Confidence Repair

V39.1 removes artificial neutrality from missing data and makes every WIS ranking auditable.

## Core changes

- Missing Form 4, 13F, or Congress/OGE pillars are represented as `N/A`, not `50`.
- WIS weights are dynamically renormalized across available pillars.
- Every ticker now reports coverage, effective sources, signal count, freshness, confidence, and a Low Coverage flag.
- Resonance is signed and classified as `BULLISH`, `BEARISH`, `CONFLICTED`, or `NONE`, with L0–L3 level and source composition.
- Risk is calculated independently from bearish evidence and is no longer `100 - WIS`.
- Opportunity rankings require two valid source pillars, except for an explicitly marked exceptional single-source case.
- HTML rankings display `N/A`, coverage, signal count, freshness, signed resonance, and resonance sources.
- A conservative CUSIP seed map resolves AMD (`007903107`), ASML (`N07059210`), and LRCX (`512807108`). Unknown CUSIPs remain excluded rather than guessed.

## Compatibility

The public functions `normalize_trades`, `score_signals`, and `build_rankings` are unchanged. `calculate_resonance` returns a richer object but still supports legacy three-value unpacking.

## Validation

Run:

```bash
python -m pytest -q
```

## Upgrade

Replace the V39.0 source tree with this package, preserve your `.env`/GitHub secrets, and run the existing workflow. No database migration is required.

## Rollback

Restore the V39.0 ZIP or previous Git commit. V39.1 does not alter the database schema.
