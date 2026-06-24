# V14 OGE Diagnostics Hotfix

This hotfix builds on V13 and focuses on diagnosing why configured OGE Trump PDF URLs may not produce parsed trades.

## Changes

- OGE URL splitting now uses only semicolon/newline separators, not commas.
- Adds masked OGE URL diagnostics to GitHub Actions logs:
  - whether `OGE_TRUMP_REPORT_URLS` is present
  - Trump URL count
  - Cabinet spec count
  - each masked URL tail
  - PDF HTTP status, content type, byte size
  - PDF page count and extracted text character count
  - parser candidate block count and normalized row count
- OGE parser is less brittle:
  - recognizes imperfect OCR variants of `purchase`
  - can infer major tickers from asset names such as Microsoft, Meta, Amazon, NVIDIA, AMD, Oracle, Apple, Alphabet, Tesla
  - still avoids treating non-stock municipal bond rows as stock signals unless a known ticker can be inferred

## Files changed

- `app/collectors/oge_executive.py`

## What to check after running

Search the Actions log for:

```text
OGE executive config
OGE Trump URL
OGE PDF fetch
OGE PDF extracted
OGE parser candidate blocks
OGE executive normalized trades
```

If `trump_url_count=2` but `normalized trades=0`, the PDF text format still needs a Trump-specific parser calibration. If `trump_url_count=0`, the Secret is not being passed to the workflow.
