# V16 - 关联 SELL 审计增强 + OGE Watcher + Trump 高亮

本版本在 V15 基础上解决三类问题：

1. **关联 SELL 审计完整性**
   - 主动买入雷达中的股票，只要同期存在 SELL，就生成关联 SELL 审计。
   - 新增“关联 SELL 汇总覆盖度”：显示 SELL 总金额、原始/去重笔数、已展示明细金额、未展开/待核对金额、主要卖出巨鲸。
   - 新增“关联 SELL 性质拆解”：按 OGE/政界、10% Owner、高管、董事、信托/基金会/家族实体、10b5-1/计划交易、税务/薪酬等角色桶聚合。
   - 明细表改为“每只股票 Top 20”，避免 MU 这类股票只露出一条明细却隐藏大量未展开卖出。

2. **OGE 自动发现 Watcher**
   - 保留 `OGE_TRUMP_REPORT_URLS` 与 `OGE_CABINET_REPORTS` 手动官方 PDF URL 配置。
   - 新增可选自动发现配置：
     - `ENABLE_OGE_AUTO_DISCOVERY=true`
     - `OGE_DISCOVERY_URLS`：OGE 官方搜索页或搜索结果页，多个用分号分隔。
     - `OGE_DISCOVERY_WATCHLIST`：实际人名 watchlist。
     - `OGE_DISCOVERY_MAX_LINKS=50`
   - 自动发现只尝试 278-T / Transaction PDF，不把 278e 年度/提名披露当成交易。

3. **Trump 黄色高亮**
   - 报告 HTML 中所有可见 `Trump`、`Donald J. Trump`、`Donald Trump`、`特朗普` 都会用黄色高亮。
   - 高亮仅作用于可见文本，不修改 HTML 标签和链接 URL。

## 覆盖文件

```text
app/config.py
app/collectors/oge_executive.py
app/main.py
app/reports/html_report.py
.github/workflows/daily_scan.yml
.env.example
README_V16_ASSOCIATED_SELL_OGE_WATCHER.md
```

## 建议变量

```text
ENABLE_OGE_AUTO_DISCOVERY=true
OGE_DISCOVERY_MAX_LINKS=50
```

`OGE_DISCOVERY_URLS` 可以先使用默认 OGE 官方集合页；更推荐把你在 OGE 搜索 Donald Trump、Scott Bessent、Marco Rubio 等得到的搜索结果页 URL 也加入，多个 URL 用分号分隔。

