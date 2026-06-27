# V19 Cabinet OGE Radar Patch

本补丁只改进 V18 中“行政分支关键人物投资标的雷达（不限美股）”的数据接入，不改变 V18 已确认的日报简报结构。

## 主要改动

1. **Cabinet OGE 不再只依赖手动 URL**
   - 新增一组官方 OGE seeded Cabinet/Cabinet-level 披露 URL。
   - 覆盖 Scott Bessent、Howard Lutnick、Chris Wright、Doug Burgum 等已知官方 OGE 278-T / 278e 文件。
   - 用户仍可通过 `OGE_CABINET_REPORTS` 或 `OGE_SEED_CABINET_REPORTS` 追加更多文件。

2. **支持 278e / Ethics / Divestiture 资产型披露**
   - 278-T 仍作为交易型披露，进入 BUY/SELL 交易统计。
   - 278e、Ethics Agreement、Certificate of Divestiture 不再被误作交易，而是进入“投资标的雷达”。
   - 对无法稳定抽出资产行的文件，会保留“已发现文件但未解析资产行”的状态行。

3. **投资标的不限美股**
   - 资产雷达可以展示基金、LLC、private fund、商业房地产、信托、ETF、债券、其它投资资产。
   - 不再强行把所有资产映射成美股 ticker。

## 新增配置

```env
OGE_SEED_CABINET_REPORTS_ENABLED=true
ENABLE_OGE_ASSET_DISCLOSURES=true

# 可选追加，多个条目用分号或换行分隔：
# Name|Position|PDF_URL|Agency|ReportType
# ReportType: OGE_278_T / OGE_278e / OGE_ETHICS_AGREEMENT / OGE_DIVESTITURE
OGE_SEED_CABINET_REPORTS=
```

## 覆盖文件

```text
app/config.py
app/collectors/oge_executive.py
.env.example
tests/test_oge_executive_parser.py
README_V19_CABINET_OGE_RADAR.md
```

## 注意

OGE 278e 是资产/持仓披露，不代表近期买入或卖出；只有 278-T 才进入交易型 BUY/SELL 图表。正式报告中会把二者分开呈现。
