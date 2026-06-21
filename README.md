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
