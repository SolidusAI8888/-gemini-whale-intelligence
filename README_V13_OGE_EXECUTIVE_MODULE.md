# V13 OGE Executive Branch 模块

本版在 V12 基础上新增 **OGE 行政分支披露模块**，用于单独追踪总统特朗普、各部长和 Cabinet-level 官员的 OGE Form 278-T / 278e 相关公开披露。

## 新增能力

- 新增 `app/collectors/oge_executive.py`
- 新增总统特朗普 OGE 投资披露专题
- 新增部长 / Cabinet OGE 披露雷达
- OGE 278-T 金额区间解析：`amount_low / amount_high / amount_mid / amount_range_label`
- 报告中对 OGE 交易使用“区间中点”排序和图表展示
- 检测并标记 `late fee`、`discretionary / managed account / trust` 文本
- 明确表述为“披露账户发生交易”，避免误写为“本人主动下单”

## 需要配置的变量

### GitHub Secrets

```text
OGE_TRUMP_REPORT_URLS = 官方 OGE / OGE-hosted 278-T PDF URL，多个用逗号或分号隔开
OGE_CABINET_REPORTS = Name|Title|PDF_URL|Agency;Name|Title|PDF_URL|Agency
```

示例：

```text
OGE_TRUMP_REPORT_URLS=https://example.oge.gov/trump-278t.pdf
OGE_CABINET_REPORTS=Scott Bessent|Secretary of the Treasury|https://example.oge.gov/bessent-278t.pdf|Treasury;Howard Lutnick|Secretary of Commerce|https://example.oge.gov/lutnick-278t.pdf|Commerce
```

### GitHub Variables

```text
ENABLE_OGE_EXECUTIVE_TRADES = true
OGE_MAX_REPORTS = 20
```

## 重要解释口径

OGE 278-T 披露的是被披露人本人、配偶或受抚养子女账户发生的证券交易。若报告文本显示 discretionary / managed account / trust，报告应表述为：

```text
特朗普披露账户发生了某股票买入/卖出
```

不应表述为：

```text
特朗普本人主动买入/卖出
```

## 覆盖文件

```text
app/config.py
app/db.py
app/main.py
app/collectors/oge_executive.py
app/reports/html_report.py
.github/workflows/daily_scan.yml
.env.example
README_V13_OGE_EXECUTIVE_MODULE.md
tests/test_oge_executive_parser.py
```
