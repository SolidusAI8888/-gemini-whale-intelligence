# V11 Report Clarity Fix

This release improves report readability and addresses questions raised from the V10 report.

## Changes

- Top Signals now show directional transaction amount columns:
  - Buy signals sorted by total BUY amount
  - Sell warning signals sorted by total SELL amount
- Added evidence tables for Top Signals:
  - Active BUY evidence, sorted by amount
  - SELL evidence, sorted by amount
- Split recent core disclosures into separate sections:
  - Recent core BUY disclosures, sorted by amount
  - Recent core SELL disclosures, sorted by amount
- Added non-core audit table:
  - option exercise / grant / tax / gift / other records
  - these do **not** count as active BUY signals
- Political disclosures remain visible and are sorted by amount.
- Gemini section now has a deterministic fallback summary if Gemini returns empty text.

## Why

The old report aggregated Top Signals over the lookback window, but the bottom “recent core BUY/SELL” table only showed a generic recent list dominated by SEC sales. This made it hard to see the underlying buy records for CRM/MELI/DIS and made the recent table look like “all sells.”

V11 makes the evidence explicit and separates active `P/BUY` from option/grant/award/exercise rows.

## Files to overwrite

- `app/analyzers/opportunity.py`
- `app/db.py`
- `app/main.py`
- `app/reports/html_report.py`

No new secrets or variables are required.
