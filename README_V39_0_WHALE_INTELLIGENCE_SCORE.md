# V39.0 — Whale Intelligence Score

This release adds a unified, rule-based Whale Intelligence Score (WIS) while preserving the legacy scoring/report pipeline.

## Frozen weights

- SEC Form 4: 20%
- Institutional 13F: 30%
- Congress / OGE: 20%
- Cross-source resonance: 30%

## New architecture

`app/intelligence/`

- `models.py` — unified Signal and WIS result models
- `signal.py` — normalizes Form 4, Congress, OGE, and 13F rows
- `registry.py` — central whale registry
- `config.py` / `weights.py` — validated configuration
- `score_engine.py` — deterministic WIS rule engine
- `resonance.py` — three-level cross-source resonance
- `ranking.py` — Top10 Opportunities, Risks, and Resonance

## Report additions

The HTML dashboard now begins with:

1. Top10 Opportunities
2. Top10 Risks
3. Top10 Most Resonant Stocks

Every row exposes total WIS, confidence, Form4 score, 13F score, Congress/OGE score, resonance level, and major actors.

## Environment overrides

- `WIS_WEIGHT_FORM4` (default `0.20`)
- `WIS_WEIGHT_13F` (default `0.30`)
- `WIS_WEIGHT_CONGRESS` (default `0.20`)
- `WIS_WEIGHT_RESONANCE` (default `0.30`)
- `WIS_TOP_N` (default `10`)
- `WIS_MAX_SIGNAL_AGE_DAYS` (default `365`)
- `WIS_MIN_AMOUNT_USD` (default `0`)

Weights must sum to 1.0 or startup raises a configuration error.

## Validation

The release includes tests for signal normalization, frozen weights, directional scoring, and three-source resonance.
