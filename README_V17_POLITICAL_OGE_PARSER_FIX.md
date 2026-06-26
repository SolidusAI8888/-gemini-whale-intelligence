# V17 Political Options + OGE Parser Fix

This release builds on V16 and focuses on parser accuracy after manual validation of Trump AVGO and Nancy Pelosi INTC/UBER/AAPL disclosures.

## What changed

1. **Trump highlight safety**
   - Yellow-highlight visible `Trump`, `Donald J. Trump`, `Donald Trump`, and `特朗普` text only inside `<body>`.
   - Does not mutate CSS selectors, HTML tags, attributes, URLs, or `<style>/<script>` blocks.

2. **OGE 278-T date and amount guardrails**
   - Repairs a common OGE extraction error where `2026` is read as `2028` when a year-2 correction produces a plausible non-future date.
   - Validates OGE amount ranges against official OGE buckets.
   - Repairs common bucket truncations such as `$1 - $5,000,000` -> `$1,000,001 - $5,000,000`.
   - Quarantines malformed fragments such as `$1 - $1` or `$1,001 - $15` when they cannot be reliably repaired.

3. **House PTR option parser**
   - Reconstructs rows split across multiple PDF text lines.
   - Prevents option expiration dates from being treated as transaction dates.
   - Extracts option metadata where possible: option type, contracts, strike price, expiration date.
   - Specifically fixes Pelosi-style rows such as INTC and UBER call-option purchases.

4. **Donor-Advised Fund / contribution handling**
   - Political PTR rows containing `Contribution` or `Donor-Advised Fund` are classified as `OTHER_TRANSFER` with code `G` instead of ordinary active SELL.
   - This prevents Pelosi AAPL donor-advised-fund transfers from being over-interpreted as ordinary market sell signals.

## Validated cases

- Trump / AVGO: official OGE disclosure contains Broadcom purchase on 2026-02-10; V17 corrects `2028` OCR drift when detected.
- Pelosi / INTC: official House PTR includes INTC call-option purchase on 2026-05-29.
- Pelosi / UBER: official House PTR includes UBER call-option purchase on 2026-05-29.
- Pelosi / AAPL: official House PTR includes 2025-12-24 sale and 2025-12-30 option purchase; 2025-12-30 donor-advised-fund contribution is no longer treated as ordinary active SELL.

## Files changed

- `app/collectors/congress.py`
- `app/collectors/oge_executive.py`
- `app/reports/html_report.py`
- `tests/test_political_collector.py`
- `tests/test_oge_executive_parser.py`
- `tests/test_report_quality.py`

## Tests

`13 passed`
