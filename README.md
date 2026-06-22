# Gemini-美股聪明钱_政商巨鲸行动追踪

这是 `whale-intelligence` 的 Gemini 独立版本。核心数据链路保持一致：SEC Form 4 → 股票池过滤 → WhaleScore / Consensus / OpportunityScore → Gemini 分析 → HTML 报告 → 可选邮件发送。

> 重要：本系统只输出公开披露研究信号，不提供个性化证券投资建议、具体仓位、买卖金额或保证收益。

## 本地运行

```bash
cp .env.example .env
# 编辑 .env，至少设置 SEC_USER_AGENT；启用 AI 时设置 GEMINI_API_KEY
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

## GitHub Actions Secrets

必填：

```text
SEC_USER_AGENT=WhaleIntelligenceGemini your_email@example.com
```

启用 Gemini：

```text
ENABLE_GEMINI=true
GEMINI_API_KEY=你的 Gemini API Key
```

邮件发送：

```text
SEND_EMAIL=true
DRY_RUN=false
SENDGRID_API_KEY=你的 SendGrid Key
EMAIL_FROM=已验证发件邮箱
EMAIL_TO=收件邮箱
```

## GitHub Actions Variables

```text
GEMINI_MODEL=gemini-2.5-pro
LOOKBACK_DAYS=3
MAX_COMPANIES=0
MIN_OPPORTUNITY_SCORE=55
```

第一次测试建议：

```text
SEND_EMAIL=false
DRY_RUN=true
```

## 说明

Gemini 只作为分析层。核心交易事实仍来自 SEC、国会披露、13F、13D/13G 等权威公开记录。

## V5: Political Whale Signals

V5 adds a political disclosure module so the report no longer relies only on SEC Form 4 corporate insiders.

Default behavior:

- `ENABLE_POLITICAL_TRADES=true`
- `POLITICAL_PROVIDER=auto`
- Official House Clerk yearly ZIP archive is parsed without an API key.
- If `FMP_API_KEY` is configured, optional FMP House/Senate latest endpoints are also queried.

Recommended GitHub Actions Variables:

```text
LOOKBACK_DAYS=365
MAX_COMPANIES=0
MIN_OPPORTUNITY_SCORE=0
GEMINI_MODEL=gemini-2.5-flash-lite
POLITICAL_PROVIDER=auto
POLITICAL_MAX_FILINGS=500
FMP_MAX_PAGES=5
FMP_PAGE_LIMIT=100
```

Recommended GitHub Actions Secrets:

```text
ENABLE_POLITICAL_TRADES=true
FMP_API_KEY=optional, for Senate + normalized House/Senate data
```

Notes:

- House official disclosure ZIPs are public and require no API key, but PDF table parsing can be imperfect.
- Senate eFD has no equally convenient official bulk machine-readable endpoint in this package, so Senate coverage is best enabled through FMP or another licensed structured provider.
- Executive-branch/OGE disclosures are not yet fully automated in V5 and should be added as a separate V6 module.


## V6: Political universe scope

If the political module is enabled but the report still shows no Pelosi/Congress trades, the records may be filtered out because they are outside the S&P 500 + Nasdaq-100 universe or are options/ETFs. Set this GitHub Actions variable for diagnostics:

```text
POLITICAL_UNIVERSE_SCOPE=all
LOOKBACK_DAYS=365
POLITICAL_PROVIDER=auto
FMP_MAX_PAGES=20
FMP_PAGE_LIMIT=100
```

Use `POLITICAL_UNIVERSE_SCOPE=core` for strict production mode, where political trades are limited to S&P 500 + Nasdaq-100 tickers. Use `all` or `both` to verify whether the political data source is returning records outside the core universe.

## V7 FMP Senate/House endpoint notes

FMP now documents both latest-disclosure and trading-activity endpoints. V7 queries:

- `senate-latest`
- `senate-trades`
- `senate-trades-by-name`
- `house-latest`
- `house-trades`
- `house-trades-by-name`

Set GitHub Variables:

```text
POLITICAL_UNIVERSE_SCOPE=all
FMP_HOUSE_ENDPOINTS=house-latest,house-trades
FMP_SENATE_ENDPOINTS=senate-latest,senate-trades
POLITICAL_WATCH_NAMES=Pelosi,Trump
FMP_MAX_PAGES=20
FMP_PAGE_LIMIT=100
LOOKBACK_DAYS=365
```

`POLITICAL_UNIVERSE_SCOPE=all` is recommended during debugging so ETF/options/non-index politician trades are visible instead of being filtered by S&P500/Nasdaq100 membership.
