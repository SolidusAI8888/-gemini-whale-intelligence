from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Iterable, Mapping

from app.config import settings


def _money(value) -> str:
    try:
        value = float(value or 0)
    except Exception:  # noqa: BLE001
        return "-"
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value/1_000:.1f}K"
    return f"${value:.0f}"


def _table(headers: list[str], rows: Iterable[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _score_rows(items: list[Mapping]) -> list[list[str]]:
    rows = []
    for item in items[:20]:
        rows.append(
            [
                f"<b>{escape(str(item['ticker']))}</b>",
                escape(str(item.get("signal_label", ""))),
                f"{float(item.get('opportunity_score') or 0):.1f}",
                f"{float(item.get('consensus_score') or 0):.1f}",
                f"{float(item.get('risk_score') or 0):.1f}",
                escape(str(item.get("explanation", ""))),
            ]
        )
    return rows


def _trade_rows(trades: list[Mapping], limit: int = 80) -> list[list[str]]:
    rows = []
    for t in trades[:limit]:
        url = t.get("filing_url") or ""
        filing = f"<a href=\"{escape(url)}\">SEC</a>" if url else "SEC"
        rows.append(
            [
                escape(str(t.get("filing_date") or "")),
                escape(str(t.get("trade_date") or "")),
                f"<b>{escape(str(t.get('ticker') or ''))}</b>",
                escape(str(t.get("action") or "")),
                escape(str(t.get("transaction_code") or "")),
                escape(str(t.get("whale_name") or "")),
                escape(str(t.get("insider_role") or "")),
                _money(t.get("amount_usd")),
                filing,
            ]
        )
    return rows


def _political_trade_rows(trades: list[Mapping], limit: int = 80) -> list[list[str]]:
    rows = []
    political = [t for t in trades if str(t.get("whale_category") or "").startswith("Political Whale") and str(t.get("action") or "") in {"BUY", "SELL"}]
    for t in political[:limit]:
        url = t.get("filing_url") or ""
        src = escape(str(t.get("source") or "POLITICAL"))
        filing = f"<a href=\"{escape(url)}\">{src}</a>" if url else src
        rows.append(
            [
                escape(str(t.get("filing_date") or "")),
                escape(str(t.get("trade_date") or "")),
                f"<b>{escape(str(t.get('ticker') or ''))}</b>",
                escape(str(t.get("action") or "")),
                escape(str(t.get("whale_name") or "")),
                escape(str(t.get("insider_role") or "")),
                _money(t.get("amount_usd")),
                filing,
            ]
        )
    return rows


def build_html_report(
    top_scores: list[Mapping],
    recent_trades: list[Mapping],
    ai_analysis: str = "",
    new_trade_count: int = 0,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    buy_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("多头")]
    sell_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("减持")]

    # For readability, the main recent-trades table focuses on P/S only.
    # Non-core A/M/F/G/J rows remain in the SQLite artifact for audit.
    core_recent_trades = [t for t in recent_trades if str(t.get("action") or "") in {"BUY", "SELL"}]
    political_recent_trades = [t for t in recent_trades if str(t.get("whale_category") or "").startswith("Political Whale") and str(t.get("action") or "") in {"BUY", "SELL"}]

    if new_trade_count == 0:
        summary = "本次扫描未发现新的披露记录。邮件不重复列出历史内容；下方如有表格，是数据库中最近留存记录。"
    else:
        summary = f"本次扫描新增 {new_trade_count} 条披露交易记录。"

    buy_table = _table(['股票', '信号', '机会分', '共识分', '风险分', '解释'], _score_rows(buy_scores)) if buy_scores else '<p>暂无主动买入类可评分信号。</p>'
    sell_table = _table(['股票', '信号', '机会分', '共识分', '风险分', '解释'], _score_rows(sell_scores)) if sell_scores else '<p>暂无减持/卖出类可评分信号。</p>'
    core_trade_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_recent_trades)) if core_recent_trades else '<p>暂无近期 BUY/SELL 核心交易记录。</p>'
    political_trade_table = _table(['披露日', '交易日', '股票', '方向', '政界巨鲸', '机构/角色', '估算金额', '来源'], _political_trade_rows(political_recent_trades)) if political_recent_trades else '<p>暂无近期政界巨鲸 BUY/SELL 交易记录。若未配置 FMP_API_KEY，当前默认仅解析官方 House ZIP；Senate/行政官员模块需要另接数据源。</p>'

    html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>Gemini-美股聪明钱_政商巨鲸行动追踪</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; line-height: 1.55; color: #111827; }}
h1 {{ color: #111827; }}
h2 {{ margin-top: 28px; }}
.badge {{ display: inline-block; padding: 3px 8px; background: #eef2ff; border-radius: 12px; }}
.notice {{ background: #fff7ed; padding: 12px; border-left: 4px solid #f97316; }}
.note {{ background: #f9fafb; padding: 10px; border-left: 4px solid #9ca3af; color: #374151; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 7px; vertical-align: top; }}
th {{ background: #f9fafb; text-align: left; }}
.small {{ color: #6b7280; font-size: 12px; }}
</style>
</head>
<body>
<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>
<p class="small">生成时间：{escape(now)}</p>
<p class="notice">{escape(summary)}</p>
<p><b>重要说明：</b>本报告是基于公开披露文件的研究筛选结果，不构成个性化投资建议。Form 4 和其他披露存在时间滞后、交易目的复杂、自动交易计划等限制。</p>
<p class="note">V5 报告把主动买入、减持/卖出、政界巨鲸信号分开展示。近期交易表默认只显示 P/BUY 与 S/SELL 核心交易；A/M/F/G/J 等授予、期权、税务、赠与或其它记录保留在随报告上传的 SQLite 数据库中，供审计追溯。</p>

<h2>主动买入 Top Signals</h2>
{buy_table}

<h2>减持/卖出预警 Top Signals</h2>
{sell_table}

<h2>政界巨鲸 BUY/SELL 披露</h2>
{political_trade_table}

<h2>近期核心 BUY/SELL 披露</h2>
{core_trade_table}

<h2>Gemini 综合分析</h2>
<pre style="white-space: pre-wrap; background:#f9fafb; padding:12px; border:1px solid #e5e7eb;">{escape(ai_analysis or '未启用。')}</pre>

<h2>评分口径</h2>
<p>V5 同时识别 SEC Form 4 公司内部人交易与政治人物披露交易。公司内部人侧重点识别 P（公开/私下买入）与 S（公开/私下卖出）；政界侧接入 House 官方披露 ZIP，并可选接入 FMP House/Senate API。CEO、CFO、董事、10% 持有人、众议员、参议员等类别按信息优势加权；金额、披露新鲜度和多巨鲸共振会提高分数。同一报告人、同一文件、同一方向的多笔拆分成交只计为一个独立事件，以降低虚假共振。</p>
</body>
</html>
"""
    return html


def save_report(html: str) -> Path:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"gemini_whale_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    return path
