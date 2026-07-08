# V33 Detail Highlight Only + 13F Consensus Analysis

## What changed

1. Necessary-detail tables keep their original amount-first ordering.
   - New rows are highlighted orange in place.
   - New rows are no longer promoted to the top of “商界巨鲸必要明细” or “政界巨鲸必要明细”.

2. Added institutional 13F consensus analysis.
   - New report subsection: `13F 共识增减持分析（最近相邻两期/约三个月）`.
   - Compares each Top 20 institutional whale's latest 13F with its immediately prior 13F.
   - Shows which issuers were increased by multiple managers, reduced by multiple managers, newly opened, or exited.
   - This is a quarter-over-quarter holding-change signal, not a same-day trade signal.

3. Strengthened 13F display normalization.
   - The report layer now repeatedly scales down stale legacy 13F amounts above $100B.
   - This prevents old cached 1000x rows from appearing as multi-trillion-dollar single positions.

## Important setting

For the consensus analysis to work, the scanner needs at least two 13F filings per manager.

Recommended GitHub Actions Variable:

```text
INSTITUTIONAL_13F_FILINGS_PER_MANAGER = 2
```

V33 changes the code default from `1` to `2`, but if your GitHub repository already has this Variable set to `1`, GitHub will override the code default. In that case, manually change it to `2`.

## Files changed

```text
app/reports/html_report.py
app/config.py
app/db.py
app/main.py
.env.example
tests/test_report_quality.py
README_V33_DETAIL_HIGHLIGHT_ONLY_AND_13F_CONSENSUS.md
```

## Validation

```text
22 passed
```
