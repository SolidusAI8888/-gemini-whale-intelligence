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


def _is_political_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("POLITICAL") or category.startswith("Political")


def _political_trade_rows(trades: list[Mapping], limit: int = 120) -> list[list[str]]:
    rows = []
    political = [
        t
        for t in trades
        if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}
    ]
    political.sort(key=lambda t: (str(t.get("filing_date") or ""), str(t.get("trade_date") or ""), str(t.get("ticker") or "")), reverse=True)
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
                escape(str(t.get("transaction_code") or "")),
                escape(str(t.get("whale_name") or "")),
                escape(str(t.get("insider_role") or t.get("whale_category") or "")),
                _money(t.get("amount_usd")),
                filing,
            ]
        )
    return rows


def _political_summary_rows(summary: list[Mapping]) -> list[list[str]]:
    rows = []
    for row in summary:
        rows.append(
            [
                escape(str(row.get("action") or "")),
                escape(str(row.get("record_count") or 0)),
                escape(str(row.get("ticker_count") or 0)),
                _money(row.get("total_amount_usd")),
            ]
        )
    return rows



def _fmt_pct(value) -> str:
    try:
        return f"{float(value):.1f}%"
    except Exception:  # noqa: BLE001
        return "-"


def _fmt_num(value, digits: int = 1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:  # noqa: BLE001
        return "-"


def _market_rows(items: list[Mapping], limit: int = 50) -> list[list[str]]:
    rows = []
    # Put rows with more complete signals first.
    def completeness(row: Mapping) -> tuple[int, str]:
        fields = ["price", "trend_score", "valuation_score", "sentiment_score", "pe_ratio", "ret_20d"]
        return (sum(1 for f in fields if row.get(f) not in (None, "")), str(row.get("ticker") or ""))
    for item in sorted(items, key=completeness, reverse=True)[:limit]:
        rows.append(
            [
                f"<b>{escape(str(item.get('ticker') or ''))}</b>",
                _money(item.get("price")),
                _fmt_pct(item.get("change_pct")),
                _fmt_pct(item.get("ret_20d")),
                _fmt_pct(item.get("ret_60d")),
                _fmt_num(item.get("pe_ratio")),
                _fmt_num(item.get("ps_ratio")),
                _fmt_num(item.get("trend_score"), 0),
                _fmt_num(item.get("valuation_score"), 0),
                _fmt_num(item.get("sentiment_score"), 0),
                escape(str(item.get("data_sources") or "")),
                escape(str(item.get("summary_note") or "")),
            ]
        )
    return rows

def build_html_report(
    top_scores: list[Mapping],
    recent_trades: list[Mapping],
    ai_analysis: str = "",
    new_trade_count: int = 0,
    political_summary: list[Mapping] | None = None,
    market_context: list[Mapping] | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    buy_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("多头")]
    sell_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("减持")]

    # For readability, the main recent-trades table focuses on P/S only.
    # Non-core A/M/F/G/J rows remain in the SQLite artifact for audit.
    core_recent_trades = [t for t in recent_trades if str(t.get("action") or "") in {"BUY", "SELL"}]
    political_recent_trades = [t for t in recent_trades if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}]

    if new_trade_count == 0:
        summary = "本次扫描未发现新的披露记录。邮件不重复列出历史内容；下方如有表格，是数据库中最近留存记录。"
    else:
        summary = f"本次扫描新增 {new_trade_count} 条披露交易记录。"

    buy_table = _table(['股票', '信号', '机会分', '共识分', '风险分', '解释'], _score_rows(buy_scores)) if buy_scores else '<p>暂无主动买入类可评分信号。</p>'
    sell_table = _table(['股票', '信号', '机会分', '共识分', '风险分', '解释'], _score_rows(sell_scores)) if sell_scores else '<p>暂无减持/卖出类可评分信号。</p>'
    core_trade_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_recent_trades)) if core_recent_trades else '<p>暂无近期 BUY/SELL 核心交易记录。</p>'
    political_trade_table = _table(['披露日', '交易日', '股票', '方向', '代码', '政界巨鲸', '机构/角色', '估算金额', '来源'], _political_trade_rows(political_recent_trades)) if political_recent_trades else '<p>暂无近期政界巨鲸 BUY/SELL 交易记录。若日志显示 Political trades collected 大于 0，请检查 action 标准化或报告查询条件。</p>'
    political_summary_table = _table(['动作', '记录数', '涉及标的数', '估算金额合计'], _political_summary_rows(political_summary or [])) if political_summary else '<p>暂无政界交易诊断汇总。</p>'
    market_table = _table(['股票', '价格', '日变动', '20日', '60日', 'PE', 'PS', '趋势分', '估值/基本面分', '情绪分', '数据源', '备注'], _market_rows(market_context or [])) if market_context else '<p>暂无行情/基本面/新闻情绪数据。请确认 ENABLE_MARKET_DATA=true，并配置 ALPHA_VANTAGE_API_KEY 或 FINNHUB_API_KEY。</p>'

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
<p class="note">V10 报告把主动买入、减持/卖出、政界巨鲸、行情/基本面/新闻情绪分开展示。政界侧默认使用免费 House 官方披露；FMP Congressional 默认关闭。行情与基本面可由 Alpha Vantage 和 Finnhub 免费 API 补充。</p>

<h2>主动买入 Top Signals</h2>
{buy_table}

<h2>减持/卖出预警 Top Signals</h2>
{sell_table}

<h2>政界巨鲸 BUY/SELL 披露</h2>
{political_trade_table}

<h2>政界交易诊断汇总</h2>
{political_summary_table}

<h2>行情 / 基本面 / 新闻情绪补充</h2>
{market_table}

<h2>近期核心 BUY/SELL 披露</h2>
{core_trade_table}

<h2>Gemini 综合分析</h2>
<pre style="white-space: pre-wrap; background:#f9fafb; padding:12px; border:1px solid #e5e7eb;">{escape(ai_analysis or '未启用。')}</pre>

<h2>评分口径</h2>
<p>V10 同时识别 SEC Form 4 公司内部人交易与政治人物披露交易，并用 Alpha Vantage / Finnhub 免费接口补充行情、趋势、估值、基本面、新闻情绪与独立 insider 数据校验。机会分仍以公开披露交易为主，行情/基本面/情绪只做小幅透明调整；本报告不构成个性化投资建议。</p>
</body>
</html>
"""
    return html


def save_report(html: str) -> Path:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"gemini_whale_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    return path
