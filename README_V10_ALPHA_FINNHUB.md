# V10：Alpha Vantage + Finnhub 免费接口增强

本版本在 V9 免费 FMP 模式基础上新增免费行情/基本面/新闻情绪模块：

- Alpha Vantage：GLOBAL_QUOTE、TIME_SERIES_DAILY、OVERVIEW
- Finnhub：quote、basic financials、news sentiment、insider transactions
- 新增 `market_snapshots` 数据表
- 报告新增「行情 / 基本面 / 新闻情绪补充」板块
- 机会分会基于趋势、估值/基本面、新闻情绪做小幅透明调整
- FMP Congressional 默认继续关闭，不会再刷 402

## 需要配置的 Secrets

```text
ALPHA_VANTAGE_API_KEY = 你的 Alpha Vantage 免费 key
FINNHUB_API_KEY = 你的 Finnhub 免费 key
```

保留原有：

```text
ENABLE_POLITICAL_TRADES = true
GEMINI_API_KEY = 你的 Gemini key
SEC_USER_AGENT = 你的联系邮箱格式 User-Agent
```

## 建议配置的 Variables

```text
ENABLE_MARKET_DATA = true
MARKET_DATA_MAX_SYMBOLS = 25
POLITICAL_PROVIDER = official_house
POLITICAL_UNIVERSE_SCOPE = all
FMP_CONGRESSIONAL_ENABLED = false
LOOKBACK_DAYS = 365
MIN_OPPORTUNITY_SCORE = 0
```

免费 API 有请求次数限制。如果运行时出现 throttle/rate limit 日志，把 `MARKET_DATA_MAX_SYMBOLS` 降到 10 或 15。

## 覆盖文件

覆盖仓库里的：

```text
app/config.py
app/db.py
app/main.py
app/collectors/market_data.py
app/reports/html_report.py
sql/schema.sql
.github/workflows/daily_scan.yml
.env.example
README.md
```

## 报告新增内容

报告里会出现：

```text
行情 / 基本面 / 新闻情绪补充
```

并展示：价格、日变动、20/60日动量、PE/PS、趋势分、估值/基本面分、新闻情绪分、数据源。

## 注意

Alpha Vantage 和 Finnhub 不替代 House/Senate 政客披露。它们用于补充行情、基本面、新闻情绪、Finnhub insider transaction 校验。政界数据仍默认使用免费 House 官方披露。
