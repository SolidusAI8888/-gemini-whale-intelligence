# Gemini Whale Intelligence System Design

## MVP 目标

尽快建立一个每天自动运行的公开披露研究系统，从 S&P 500 + Nasdaq-100 股票池中筛选内部人交易和巨鲸共识信号。

## V1 数据范围

- S&P 500 成分股
- Nasdaq-100 成分股
- SEC Form 4

## 标准化交易字段

- ticker
- company_name
- cik
- accession_number
- filing_url
- whale_name
- whale_category
- insider_role
- action
- transaction_code
- amount_usd
- shares
- price
- trade_date
- filing_date
- source

## 交易代码解释

- P：公开市场或私下买入，强多头信号
- S：公开市场或私下卖出，减持/空头风险信号
- A：授予/奖励，低权重
- D：向发行人处置，低权重
- M：期权行权/转换，低权重
- F：税务扣缴/支付，低权重
- G：礼物，低权重

## 后续扩展

### V2

- 13D/13G 激进持仓
- 13F 大型机构持仓变化
- 国会交易结构化 API
- 行情与波动率
- 财报增长和估值

### V3

- 巨鲸历史胜率/alpha 回测
- 行业事件图谱
- 多源交叉验证
- 自动异常检测
- 更细的投资组合级风险控制
