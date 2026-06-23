# V9 Free FMP Mode

This patch keeps FMP congressional House/Senate endpoints disabled by default because they returned `402 Payment Required` under the current key.

The political module will continue using the free official House Clerk ZIP/PDF source. The HTML report fix from V8 remains, so `POLITICAL_HOUSE` BUY/SELL records are displayed.

## Files to overwrite

```text
app/config.py
app/collectors/congress.py
.github/workflows/daily_scan.yml
.env.example
README.md
```

## GitHub Variables

```text
POLITICAL_PROVIDER=official_house
POLITICAL_UNIVERSE_SCOPE=all
FMP_CONGRESSIONAL_ENABLED=false
LOOKBACK_DAYS=365
MIN_OPPORTUNITY_SCORE=0
```

Secrets can keep `FMP_API_KEY`, but it will not be used for paid congressional endpoints unless you later set:

```text
FMP_CONGRESSIONAL_ENABLED=true
```
