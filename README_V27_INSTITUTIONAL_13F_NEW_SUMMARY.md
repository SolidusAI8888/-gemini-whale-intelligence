# V27 Institutional 13F + New Changes Summary

本版在 V26 基础上只调整报告口径与新增数据源，不改 iCloud SMTP、每日发送闸门、OGE seed、House/Senate、SEC Form 4 主流程。

## 1. 今日新增内容总览

报告首页新增“今日新增内容总览（相对上一轮成功运行）”。该表只展示相对上一轮持久化数据库快照新插入的记录，覆盖：

- 商界巨鲸 BUY/SELL
- 政界巨鲸 BUY/SELL
- 行政分支 OGE 资产/持仓披露
- 机构巨鲸 13F 持仓披露

新增记录在首页摘要和正文中整行橙色高亮。

## 2. OGE HOLDING 从政界交易明细移除

`OGE_EXECUTIVE_ASSET`、`HOLDING`、278e、Ethics Agreement、Divestiture 等资产/持仓披露不再进入“政界巨鲸必要明细”。

它们统一进入“行政分支关键人物投资标的雷达（不限美股）”。这样可以避免把 JD Vance、Cabinet 成员的 278e 资产、负债、基金、LLC、Bitcoin 等持仓误写成交易。

## 3. 政界交易日期校验

“政界巨鲸必要明细”只展示真实交易型记录：

- House / Senate PTR 的 BUY / SELL / EXCHANGE
- OGE 278-T 的 BUY / SELL / EXCHANGE

交易日期必须落在 `SCAN_START_DATE` 至当前日期之间。未来日期、期权到期日、报告期日期等不会作为正常交易日进入交易明细。

## 4. 行政分支 OGE 资产/持仓新增摘要

首页新增摘要表会显示当天新发现的 OGE 资产/持仓披露，例如：

- 人物
- 标的/资产
- HOLDING / DISCLOSURE
- 估值区间或金额中点
- 披露/报告日期
- 来源

## 5. 新增 SEC 13F 机构巨鲸模块

新增 collector：`app/collectors/sec_13f.py`。

该模块从 SEC EDGAR 13F-HR / 13F-HR/A 中读取信息表，存为 `INSTITUTIONAL_13F` / `HOLDING_13F` 记录。

13F 是季度持仓披露，不是实时买入/卖出交易。因此报告展示：

- 机构
- 代表人物
- 标的
- 发行人
- 13F 市值
- 股数
- 报告期
- 披露日
- 来源

## 6. 默认 Top 20 机构巨鲸 watchlist

默认启用的 Top 20 机构巨鲸覆盖价值、集中持仓、activist、事件驱动、科技成长、多策略等代表性机构：

1. Berkshire Hathaway / Warren Buffett
2. Pershing Square Capital Management / Bill Ackman
3. Appaloosa LP / David Tepper
4. Third Point LLC / Dan Loeb
5. Baupost Group / Seth Klarman
6. Greenlight Capital / David Einhorn
7. Scion Asset Management / Michael Burry
8. Duquesne Family Office / Stanley Druckenmiller
9. Soros Fund Management
10. Coatue Management / Philippe Laffont
11. Tiger Global Management / Chase Coleman
12. Lone Pine Capital
13. D1 Capital Partners / Dan Sundheim
14. Viking Global Investors
15. Maverick Capital
16. Point72 Asset Management / Steve Cohen
17. Bridgewater Associates
18. Elliott Investment Management / Paul Singer
19. Icahn Capital / Carl Icahn
20. Trian Fund Management / Nelson Peltz

这会覆盖 Bill Ackman / Pershing Square / Uber 这类 13F 持仓披露。

## 7. 新增配置

默认已启用，无需新增变量即可运行：

```env
ENABLE_INSTITUTIONAL_13F=true
INSTITUTIONAL_13F_MAX_MANAGERS=20
INSTITUTIONAL_13F_FILINGS_PER_MANAGER=1
INSTITUTIONAL_13F_MAX_HOLDINGS_PER_FILING=25
```

可选自定义 watchlist：

```env
INSTITUTIONAL_13F_WATCHLIST=Manager Name|CIK|Lead Investor|Style
```

多行或分号分隔均可。

## 8. 修改文件

- `app/collectors/sec_13f.py`
- `app/config.py`
- `app/db.py`
- `app/main.py`
- `app/reports/html_report.py`
- `.github/workflows/daily_scan.yml`
- `.env.example`
- `tests/test_sec_13f_collector.py`
- `tests/test_report_quality.py`

测试：`19 passed`。
