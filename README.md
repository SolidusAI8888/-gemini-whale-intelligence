# Gemini-美股聪明钱_政商巨鲸行动追踪

一个用于跟踪 S&P 500 + Nasdaq-100 范围内公开披露“聪明钱/政商巨鲸”交易行为的研究系统 MVP。

当前 V1 已实现：

- 股票池：自动读取 S&P 500 与 Nasdaq-100 成分股，并映射 SEC CIK
- 数据源：SEC EDGAR Form 4 内部人交易披露
- 解析：交易人、角色、交易代码、方向、股数、价格、估算金额、披露链接
- 分析：WhaleScore、共识分、机会分、风险分
- 报告：HTML 日报
- 邮件：SendGrid 可选发送
- 调度：GitHub Actions 每日 08:00 德国夏令时附近运行
- AI：Gemini 综合分析可选启用

> 重要：本系统只输出公开披露研究信号，不提供个性化证券投资建议、具体仓位、买卖金额或保证收益。

---

## 1. 本地 Mac 运行

```bash
cp .env.example .env
# 编辑 .env，至少设置 SEC_USER_AGENT，例如：
# SEC_USER_AGENT=GeminiWhaleIntelligence your_email@example.com

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app/main.py
```

报告会生成在：

```text
data/reports/
```

SQLite 数据库在：

```text
data/whale.db
```

---

## 2. Docker 运行

```bash
cp .env.example .env
# 编辑 .env

docker compose up --build
```

---

## 3. GitHub Actions 自动运行

把本仓库上传到 GitHub 后，进入：

```text
Repository → Settings → Secrets and variables → Actions
```

建议添加以下 Secrets：

| 名称 | 必填 | 示例 |
|---|---:|---|
| SEC_USER_AGENT | 是 | GeminiWhaleIntelligence you@example.com |
| SEND_EMAIL | 否 | true |
| DRY_RUN | 否 | false |
| SENDGRID_API_KEY | 发邮件时必填 | SG.xxx |
| EMAIL_FROM | 发邮件时必填 | reports@yourdomain.com |
| EMAIL_TO | 发邮件时必填 | you@example.com |
| ENABLE_GEMINI | 否 | true |
| GEMINI_API_KEY | 启用 Gemini 时必填 | AIza... |

可选 Variables：

| 名称 | 默认值 | 说明 |
|---|---:|---|
| LOOKBACK_DAYS | 3 | 回看最近几天披露 |
| MAX_COMPANIES | 0 | 0 表示扫描全部股票池；测试时可设 20 |
| MIN_OPPORTUNITY_SCORE | 55 | 报告展示门槛 |
| GEMINI_MODEL | gemini-1.5-pro | Gemini 模型名 |

GitHub Actions 工作流文件：

```text
.github/workflows/daily_scan.yml
```

---

## 4. 数据源说明

### SEC Form 4

Form 4 披露公司内部人、董事、高管、10% 持有人等人的权益交易。V1 重点识别交易代码：

- `P`：公开市场或私下买入
- `S`：公开市场或私下卖出

其它代码也会入库，但评分权重较低，因为它们可能对应授予、期权行权、税务扣缴、礼物等非主动交易。

### 国会交易

V1 预留 `app/collectors/congress.py` 接口，但默认不抓取。原因是 House/Senate 官方披露多为网页/PDF/表单，结构比 SEC JSON/XML 更不稳定。后续可以接入：

- 官方披露导出文件
- Quiver Quantitative API
- Capitol Trades API
- 手动下载的披露文件解析器

---

## 5. 评分逻辑

机会分不是买卖建议。V1 使用以下研究信号：

- 巨鲸类别信息优势：CEO、CFO、董事、10% 持有人等
- 交易方向：主动买入/主动卖出权重大于授予、期权、税务类交易
- 金额规模：估算金额越大，信号越强
- 披露新鲜度：越新越强
- 共识：同一股票上多个独立内部人/类别出现同向交易，分数上升

V1 暂未接入：

- 实时行情
- 技术面
- 估值
- 财报增长
- 行业景气
- 13F
- 13D/13G
- 国会交易结构化数据

这些会放入 V2/V3。

---

## 6. 目录结构

```text
app/
  collectors/       数据采集
  analyzers/        打分与共识分析
  reports/          HTML 与邮件
  llm/              Gemini 可选分析
sql/                SQLite schema
data/               本地数据库与报告输出
docs/               设计文档
.github/workflows/  GitHub Actions 定时任务
```

---

## 7. 合规与限制

- 遵守 SEC fair-access 要求：必须设置有效 User-Agent。
- 不要高频并发请求 SEC；默认限速低于 10 requests/second。
- 本报告只用于研究筛选，不应单独作为交易依据。
- Form 4、13F、国会交易披露均有天然延迟，且交易原因可能并非基本面判断。
