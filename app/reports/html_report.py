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
    if value >= 1_000_000_000:
        return f"${value/1_000_000_000:.2f}B"
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


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _score_rows(items: list[Mapping], direction: str) -> list[list[str]]:
    rows = []
    amount_key = "buy_amount" if direction == "BUY" else "sell_amount"
    event_key = "unique_buy_events" if direction == "BUY" else "unique_sell_events"
    count_key = "buy_count" if direction == "BUY" else "sell_count"
    sorted_items = sorted(
        items,
        key=lambda x: (_safe_float(x.get(amount_key)), _safe_float(x.get("opportunity_score"))),
        reverse=True,
    )
    for item in sorted_items[:20]:
        rows.append(
            [
                f"<b>{escape(str(item['ticker']))}</b>",
                escape(str(item.get("signal_label", ""))),
                _money(item.get(amount_key)),
                escape(str(item.get(count_key, ""))),
                escape(str(item.get(event_key, ""))),
                f"{float(item.get('opportunity_score') or 0):.1f}",
                f"{float(item.get('consensus_score') or 0):.1f}",
                f"{float(item.get('risk_score') or 0):.1f}",
                escape(str(item.get("explanation", ""))),
            ]
        )
    return rows


def _trade_rows(trades: list[Mapping], limit: int = 80, source_label: str = "SEC") -> list[list[str]]:
    rows = []
    sorted_trades = sorted(
        trades,
        key=lambda t: (_safe_float(t.get("amount_usd")), str(t.get("filing_date") or ""), str(t.get("trade_date") or "")),
        reverse=True,
    )
    for t in sorted_trades[:limit]:
        url = t.get("filing_url") or ""
        src = escape(str(t.get("source") or source_label))
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


def _is_political_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("POLITICAL") or category.startswith("Political")


def _political_trade_rows(trades: list[Mapping], limit: int = 120) -> list[list[str]]:
    political = [
        t
        for t in trades
        if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}
    ]
    return _trade_rows(political, limit=limit, source_label="POLITICAL")


def _political_summary_rows(summary: list[Mapping]) -> list[list[str]]:
    rows = []
    for row in sorted(summary, key=lambda r: _safe_float(r.get("total_amount_usd")), reverse=True):
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
    def market_sort(row: Mapping) -> tuple[float, float, str]:
        # No transaction amount in this section; sort by market signal strength instead.
        return (_safe_float(row.get("trend_score")), _safe_float(row.get("valuation_score")), str(row.get("ticker") or ""))
    for item in sorted(items, key=market_sort, reverse=True)[:limit]:
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


def _auto_analysis(top_scores: list[Mapping], buy_evidence: list[Mapping], sell_evidence: list[Mapping], political: list[Mapping]) -> str:
    """Deterministic fallback so the report is never blank when Gemini returns no text."""
    buy_scores = sorted(
        [x for x in top_scores if str(x.get("signal_label", "")).startswith("多头")],
        key=lambda x: _safe_float(x.get("buy_amount")),
        reverse=True,
    )
    sell_scores = sorted(
        [x for x in top_scores if str(x.get("signal_label", "")).startswith("减持")],
        key=lambda x: _safe_float(x.get("sell_amount")),
        reverse=True,
    )
    lines = [
        "Gemini 未返回可用正文，以下为系统按结构化披露自动生成的规则摘要。",
        "",
        "1. 主动买入信号：",
    ]
    if buy_scores:
        for x in buy_scores[:5]:
            lines.append(f"- {x.get('ticker')}: 买入金额约 {_money(x.get('buy_amount'))}，买入记录 {x.get('buy_count', 0)} 笔，独立买入事件 {x.get('unique_buy_events', 0)} 起。")
    else:
        lines.append("- 未发现可评分的 P/BUY 主动买入信号。")
    lines.append("")
    lines.append("2. 减持/卖出预警：")
    if sell_scores:
        for x in sell_scores[:8]:
            lines.append(f"- {x.get('ticker')}: 卖出金额约 {_money(x.get('sell_amount'))}，卖出记录 {x.get('sell_count', 0)} 笔，独立卖出事件 {x.get('unique_sell_events', 0)} 起。")
    else:
        lines.append("- 未发现可评分的 S/SELL 减持信号。")
    lines.append("")
    lines.append("3. 明细校验：")
    if buy_evidence:
        top = buy_evidence[0]
        lines.append(f"- 最大主动买入明细：{top.get('ticker')} / {top.get('whale_name')} / {_money(top.get('amount_usd'))}。")
    if sell_evidence:
        top = sell_evidence[0]
        lines.append(f"- 最大卖出明细：{top.get('ticker')} / {top.get('whale_name')} / {_money(top.get('amount_usd'))}。")
    if political:
        p = political[0]
        lines.append(f"- 最大政界披露明细：{p.get('ticker')} / {p.get('whale_name')} / {p.get('action')} / {_money(p.get('amount_usd'))}。")
    lines.append("")
    lines.append("4. 风险提示：Form 4 的 M/A/F/G/J 常代表期权行权、授予、税务扣缴、赠与或其它非主动交易；本报告的核心 BUY 只统计 P/BUY，核心 SELL 只统计 S/SELL。")
    return "\n".join(lines)


def build_html_report(
    top_scores: list[Mapping],
    recent_trades: list[Mapping],
    ai_analysis: str = "",
    new_trade_count: int = 0,
    political_summary: list[Mapping] | None = None,
    market_context: list[Mapping] | None = None,
    buy_evidence: list[Mapping] | None = None,
    sell_evidence: list[Mapping] | None = None,
    core_buy_trades: list[Mapping] | None = None,
    core_sell_trades: list[Mapping] | None = None,
    noncore_trades: list[Mapping] | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    buy_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("多头")]
    sell_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("减持")]

    core_buy_trades = core_buy_trades or [t for t in recent_trades if str(t.get("action") or "") == "BUY" and not _is_political_trade(t)]
    core_sell_trades = core_sell_trades or [t for t in recent_trades if str(t.get("action") or "") == "SELL" and not _is_political_trade(t)]
    political_recent_trades = [t for t in recent_trades if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}]
    buy_evidence = buy_evidence or []
    sell_evidence = sell_evidence or []
    noncore_trades = noncore_trades or []

    if new_trade_count == 0:
        summary = "本次扫描未发现新的披露记录。邮件不重复列出历史内容；下方如有表格，是数据库中最近留存记录。"
    else:
        summary = f"本次扫描新增 {new_trade_count} 条披露交易记录。"

    buy_table = _table(['股票', '信号', '买入金额', '买入笔数', '独立买入事件', '机会分', '共识分', '风险分', '解释'], _score_rows(buy_scores, "BUY")) if buy_scores else '<p>暂无主动买入类可评分信号。</p>'
    sell_table = _table(['股票', '信号', '卖出金额', '卖出笔数', '独立卖出事件', '机会分', '共识分', '风险分', '解释'], _score_rows(sell_scores, "SELL")) if sell_scores else '<p>暂无减持/卖出类可评分信号。</p>'
    buy_evidence_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(buy_evidence, limit=80)) if buy_evidence else '<p>暂无可展示的主动买入明细。</p>'
    sell_evidence_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(sell_evidence, limit=80)) if sell_evidence else '<p>暂无可展示的减持/卖出明细。</p>'
    core_buy_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_buy_trades, limit=80)) if core_buy_trades else '<p>暂无近期核心 BUY 交易记录。</p>'
    core_sell_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_sell_trades, limit=80)) if core_sell_trades else '<p>暂无近期核心 SELL 交易记录。</p>'
    noncore_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(noncore_trades, limit=60)) if noncore_trades else '<p>暂无近期非主动/期权/授予类披露记录。</p>'
    political_trade_table = _table(['披露日', '交易日', '股票', '方向', '代码', '政界巨鲸', '机构/角色', '估算金额', '来源'], _political_trade_rows(political_recent_trades)) if political_recent_trades else '<p>暂无近期政界巨鲸 BUY/SELL 交易记录。</p>'
    political_summary_table = _table(['动作', '记录数', '涉及标的数', '估算金额合计'], _political_summary_rows(political_summary or [])) if political_summary else '<p>暂无政界交易诊断汇总。</p>'
    market_table = _table(['股票', '价格', '日变动', '20日', '60日', 'PE', 'PS', '趋势分', '估值/基本面分', '情绪分', '数据源', '备注'], _market_rows(market_context or [])) if market_context else '<p>暂无行情/基本面/新闻情绪数据。请确认 ENABLE_MARKET_DATA=true，并配置 ALPHA_VANTAGE_API_KEY 或 FINNHUB_API_KEY。</p>'
    ai_text = str(ai_analysis or "").strip()
    if not ai_text or ai_text in {"Gemini 没有返回分析内容。", "未启用。"}:
        ai_text = _auto_analysis(top_scores, buy_evidence, sell_evidence, political_recent_trades)

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
<p class="note">V11 报告把 Top Signals 与底层明细分开展示。Top Signals 是按 {escape(str(settings.lookback_days))} 天窗口聚合后的评分；明细表按估算交易金额降序排列。核心 BUY 只统计 P/BUY，核心 SELL 只统计 S/SELL；M/A/F/G/J 等期权行权、授予、税务、赠与或其它非主动记录单独列入审计表，不混入主动买入。</p>

<h2>主动买入 Top Signals（按买入金额）</h2>
{buy_table}

<h2>主动买入明细佐证（按金额）</h2>
{buy_evidence_table}

<h2>减持/卖出预警 Top Signals（按卖出金额）</h2>
{sell_table}

<h2>减持/卖出明细佐证（按金额）</h2>
{sell_evidence_table}

<h2>政界巨鲸 BUY/SELL 披露（按金额）</h2>
{political_trade_table}

<h2>政界交易诊断汇总</h2>
{political_summary_table}

<h2>行情 / 基本面 / 新闻情绪补充</h2>
{market_table}

<h2>近期核心 BUY 披露（{escape(str(settings.lookback_days))} 天，按金额）</h2>
{core_buy_table}

<h2>近期核心 SELL 披露（{escape(str(settings.lookback_days))} 天，按金额）</h2>
{core_sell_table}

<h2>近期非主动 / 期权 / 授予 / 税务披露（审计，不计入主动 BUY）</h2>
{noncore_table}

<h2>Gemini 综合分析</h2>
<pre style="white-space: pre-wrap; background:#f9fafb; padding:12px; border:1px solid #e5e7eb;">{escape(ai_text)}</pre>

<h2>评分口径</h2>
<p>V11 同时识别 SEC Form 4 公司内部人交易与政治人物披露交易，并用 Alpha Vantage / Finnhub 免费接口补充行情、趋势、估值、基本面、新闻情绪与独立 insider 数据校验。机会分仍以公开披露交易为主，行情/基本面/情绪只做小幅透明调整；本报告不构成个性化投资建议。</p>
</body>
</html>
"""
    return html


def save_report(html: str) -> Path:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"gemini_whale_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    return path
