from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
import json
import re
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


def _is_political_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("POLITICAL") or category.startswith("Political")


def _is_oge_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("OGE_EXECUTIVE") or category.startswith("Executive:")


def _raw_json_obj(t: Mapping) -> dict:
    raw = str(t.get("raw_json") or "")
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _market_price_map(market_context: list[Mapping] | None) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in market_context or []:
        ticker = str(row.get("ticker") or "").upper()
        price = _safe_float(row.get("price"))
        if ticker and price > 0:
            prices[ticker] = price
    return prices


def _raw_json_text(t: Mapping) -> str:
    raw = str(t.get("raw_json") or "")
    obj = _raw_json_obj(t)
    if obj:
        parts = [
            str(obj.get("line") or ""),
            str(obj.get("context") or ""),
            str(obj.get("parser_block") or ""),
            str(obj.get("asset_name") or ""),
        ]
        return " ".join(parts)
    return raw


def _extract_int(pattern: str, text: str) -> int | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return int(m.group(1).replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def _extract_float(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text, re.I)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except Exception:  # noqa: BLE001
        return None


def _trade_amount_for_display(t: Mapping, price_by_ticker: dict[str, float] | None = None) -> tuple[float, str, str]:
    """Return (sortable amount, display text, quality note).

    Political PDFs often expose stock share counts, option contracts, strike
    price, or OCR fragments before the formal dollar range is captured.  When a
    political amount looks like a strike/quantity rather than a disclosed dollar
    range, estimate notional value for ranking/charts and mark it as estimated.
    """
    base = _safe_float(t.get("amount_usd"))
    if _is_oge_trade(t):
        obj = _raw_json_obj(t)
        label = str(obj.get("amount_range_label") or "").strip()
        notes = []
        if obj.get("late_fee_flag"):
            notes.append("late fee")
        if obj.get("discretionary_account_flag"):
            notes.append("discretionary/managed")
        note = "；".join(notes)
        if label:
            return base, f"{label} 中点{_money(base)}", note
        return base, _money(base), note
    if not _is_political_trade(t):
        return base, _money(base), ""

    text = _raw_json_text(t)
    ticker = str(t.get("ticker") or "").upper()
    price = (price_by_ticker or {}).get(ticker, 0.0)
    lower = text.lower()

    contracts = _extract_int(r"(\d[\d,]*)\s+(?:call|put)\s+options?", lower)
    strike = _extract_float(r"strike price of\s*\$?([\d,.]+)", lower)
    if contracts and strike:
        notional = contracts * 100 * strike
        if notional > max(base * 3, 1000):
            return notional, f"≈{_money(notional)} 名义", "期权名义估算"

    shares = _extract_int(r"(?:purchased|sold|exercised)\s+(\d[\d,]*)\s+shares?", lower)
    if not shares:
        shares = _extract_int(r"\((\d[\d,]*)\s+shares?\)", lower)
    if shares and price > 0:
        est = shares * price
        if est > max(base * 3, 1000):
            return est, f"≈{_money(est)} 估算", "按股数×当前价估算"

    if base <= 1000 and ("option" in lower or "strike" in lower):
        return base, f"{_money(base)}?", "疑似 strike/数量，待人工复核"
    return base, _money(base), ""


def _sort_grouped_trades(trades: list[Mapping], price_by_ticker: dict[str, float] | None = None, buy_first: bool = False) -> list[Mapping]:
    groups: dict[tuple[str, str], list[Mapping]] = defaultdict(list)
    for t in trades:
        action = str(t.get("action") or "").upper()
        ticker = str(t.get("ticker") or "").upper()
        if ticker:
            key_action = action if buy_first else "ALL"
            groups[(key_action, ticker)].append(t)

    def group_total(rows: list[Mapping]) -> float:
        return sum(_trade_amount_for_display(r, price_by_ticker)[0] for r in rows)

    ordered_keys = sorted(
        groups,
        key=lambda k: (
            0 if (buy_first and k[0] == "BUY") else 1 if buy_first else 0,
            group_total(groups[k]),
            k[1],
        ),
        reverse=False,
    )
    if not buy_first:
        ordered_keys = sorted(groups, key=lambda k: (group_total(groups[k]), k[1]), reverse=True)
    else:
        ordered_keys = sorted(groups, key=lambda k: (0 if k[0] == "BUY" else 1, -group_total(groups[k]), k[1]))

    ordered: list[Mapping] = []
    for key in ordered_keys:
        rows = sorted(
            groups[key],
            key=lambda t: (_trade_amount_for_display(t, price_by_ticker)[0], str(t.get("filing_date") or ""), str(t.get("trade_date") or "")),
            reverse=True,
        )
        ordered.extend(rows)
    return ordered


def _score_rows(items: list[Mapping], direction: str) -> list[list[str]]:
    rows = []
    amount_key = "buy_amount" if direction == "BUY" else "sell_amount"
    event_key = "unique_buy_events" if direction == "BUY" else "unique_sell_events"
    count_key = "buy_count" if direction == "BUY" else "sell_count"
    economic_key = "buy_economic_count" if direction == "BUY" else "sell_economic_count"
    sorted_items = sorted(
        items,
        key=lambda x: (_safe_float(x.get(amount_key)), _safe_float(x.get("opportunity_score"))),
        reverse=True,
    )
    for item in sorted_items[:25]:
        rows.append(
            [
                f"<b>{escape(str(item['ticker']))}</b>",
                escape(str(item.get("signal_label", ""))),
                _money(item.get(amount_key)),
                escape(str(item.get(count_key, ""))),
                escape(str(item.get(economic_key, item.get(count_key, "")))),
                escape(str(item.get(event_key, ""))),
                f"{float(item.get('opportunity_score') or 0):.1f}",
                f"{float(item.get('consensus_score') or 0):.1f}",
                f"{float(item.get('risk_score') or 0):.1f}",
                escape(str(item.get("explanation", ""))),
            ]
        )
    return rows


def _trade_rows(trades: list[Mapping], limit: int = 80, source_label: str = "SEC", price_by_ticker: dict[str, float] | None = None, buy_first: bool = False) -> list[list[str]]:
    rows = []
    sorted_trades = _sort_grouped_trades(trades, price_by_ticker=price_by_ticker, buy_first=buy_first)
    current_ticker = None
    for t in sorted_trades[:limit]:
        url = t.get("filing_url") or ""
        src = escape(str(t.get("source") or source_label))
        filing = f"<a href=\"{escape(url)}\">{src}</a>" if url else src
        ticker = str(t.get("ticker") or "")
        show_ticker = f"<b>{escape(ticker)}</b>"
        if ticker == current_ticker:
            show_ticker = f"<span class=\"small\">↳ {escape(ticker)}</span>"
        else:
            current_ticker = ticker
        amount_sort, amount_display, amount_note = _trade_amount_for_display(t, price_by_ticker)
        amount_html = escape(amount_display)
        if amount_note:
            amount_html += f"<br><span class=\"small\">{escape(amount_note)}</span>"
        rows.append(
            [
                escape(str(t.get("filing_date") or "")),
                escape(str(t.get("trade_date") or "")),
                show_ticker,
                escape(str(t.get("action") or "")),
                escape(str(t.get("transaction_code") or "")),
                escape(str(t.get("whale_name") or "")),
                escape(str(t.get("insider_role") or t.get("whale_category") or "")),
                amount_html,
                filing,
            ]
        )
    return rows


def _political_trade_rows(trades: list[Mapping], limit: int = 160, price_by_ticker: dict[str, float] | None = None) -> list[list[str]]:
    political = [
        t
        for t in trades
        if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}
    ]
    return _trade_rows(political, limit=limit, source_label="POLITICAL", price_by_ticker=price_by_ticker, buy_first=True)


def _political_summary_rows(summary: list[Mapping]) -> list[list[str]]:
    rows = []
    for row in sorted(summary, key=lambda r: (str(r.get("action") or "") != "BUY", -_safe_float(r.get("total_amount_usd")))):
        note = ""
        if _safe_float(row.get("total_amount_usd")) < 100_000 and str(row.get("action") or "") == "BUY":
            note = "<br><span class=\"small\">House PDF 金额字段可能为区间/OCR/期权名义，需结合明细估算。</span>"
        rows.append(
            [
                escape(str(row.get("action") or "")),
                escape(str(row.get("record_count") or 0)),
                escape(str(row.get("ticker_count") or 0)),
                _money(row.get("total_amount_usd")) + note,
            ]
        )
    return rows




def _oge_action_summary_rows(summary: list[Mapping]) -> list[list[str]]:
    rows = []
    for row in sorted(summary, key=lambda r: (str(r.get("whale_name") or ""), str(r.get("action") or ""))):
        rows.append([
            escape(str(row.get("whale_name") or "")),
            escape(str(row.get("insider_role") or "")),
            escape(str(row.get("action") or "")),
            escape(str(row.get("record_count") or 0)),
            escape(str(row.get("ticker_count") or 0)),
            _money(row.get("total_amount_usd")),
        ])
    return rows


def _oge_watchlist_rows(processed_names: set[str]) -> list[list[str]]:
    rows = []
    for name in [x.strip() for x in str(settings.oge_executive_watchlist or "").split(",") if x.strip()]:
        status = "已处理披露" if name in processed_names or any(name.lower() in p.lower() for p in processed_names) else "待配置/待发现 OGE PDF"
        rows.append([escape(name), escape(status)])
    return rows


def _trump_overview_rows(trades: list[Mapping], price_by_ticker: dict[str, float]) -> list[list[str]]:
    rows = []
    by_action: dict[str, list[Mapping]] = defaultdict(list)
    for t in trades:
        by_action[str(t.get("action") or "").upper()].append(t)
    for action in ["BUY", "SELL", "EXCHANGE"]:
        items = by_action.get(action, [])
        if not items:
            continue
        total = sum(_trade_amount_for_display(t, price_by_ticker)[0] for t in items)
        rows.append([action, str(len(items)), str(len({str(t.get("ticker") or "") for t in items})), _money(total)])
    return rows


def _oge_notice(trades: list[Mapping]) -> str:
    if not trades:
        return ""
    any_late = False
    any_discretionary = False
    urls = set()
    for t in trades:
        obj = _raw_json_obj(t)
        any_late = any_late or bool(obj.get("late_fee_flag"))
        any_discretionary = any_discretionary or bool(obj.get("discretionary_account_flag"))
        if t.get("filing_url"):
            urls.add(str(t.get("filing_url")))
    parts = []
    if any_late:
        parts.append("检测到 late fee / 逾期相关标记。")
    if any_discretionary:
        parts.append("检测到 discretionary / managed account / trust 等委托或信托相关文本；报告应表述为“披露账户发生交易”，不可直接写成本人主动下单。")
    parts.append(f"来源 PDF 数：{len(urls)}。金额使用 OGE 区间中点，仅用于排序和图表。")
    return '<p class="small">' + escape(" ".join(parts)) + '</p>'

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


def _chart_rows(trades: list[Mapping], price_by_ticker: dict[str, float], actions: set[str] | None = None, top_tickers: int = 10, buy_first: bool = False) -> str:
    rows = [t for t in trades if not actions or str(t.get("action") or "").upper() in actions]
    if not rows:
        return "<p>暂无可绘制图表的数据。</p>"
    ticker_totals: dict[str, float] = defaultdict(float)
    for t in rows:
        ticker = str(t.get("ticker") or "").upper()
        if ticker:
            ticker_totals[ticker] += _trade_amount_for_display(t, price_by_ticker)[0]
    top = {k for k, _ in sorted(ticker_totals.items(), key=lambda kv: kv[1], reverse=True)[:top_tickers]}
    rows = [t for t in rows if str(t.get("ticker") or "").upper() in top]
    items = []
    max_amt = 1.0
    for t in rows:
        amt = _trade_amount_for_display(t, price_by_ticker)[0]
        max_amt = max(max_amt, amt)
        items.append((str(t.get("ticker") or "").upper(), str(t.get("action") or "").upper(), str(t.get("whale_name") or ""), amt))
    # group by ticker then action/whale
    agg: dict[tuple[str, str, str], float] = defaultdict(float)
    for ticker, action, whale, amt in items:
        agg[(ticker, action, whale)] += amt
    ticker_order = sorted(top, key=lambda x: ticker_totals[x], reverse=True)
    html = ['<div class="chart">']
    for ticker in ticker_order:
        buy_total = sum(v for (tk, act, _), v in agg.items() if tk == ticker and act == "BUY")
        sell_total = sum(v for (tk, act, _), v in agg.items() if tk == ticker and act == "SELL")
        html.append(f'<div class="chart-group"><div class="chart-title"><b>{escape(ticker)}</b> <span class="small">BUY {escape(_money(buy_total))} / SELL {escape(_money(sell_total))}</span></div>')
        sub = [((tk, act, whale), v) for (tk, act, whale), v in agg.items() if tk == ticker]
        if buy_first:
            sub.sort(key=lambda kv: (0 if kv[0][1] == "BUY" else 1, -kv[1], kv[0][2]))
        else:
            sub.sort(key=lambda kv: -kv[1])
        for (_, action, whale), amt in sub[:12]:
            width = max(2, min(100, amt / max_amt * 100))
            cls = "buy" if action == "BUY" else "sell" if action == "SELL" else "other"
            html.append(
                f'<div class="bar-row"><div class="bar-label">{escape(action)} · {escape(whale[:42])}</div>'
                f'<div class="bar-track"><div class="bar {cls}" style="width:{width:.1f}%"></div></div>'
                f'<div class="bar-value">{escape(_money(amt))}</div></div>'
            )
        html.append('</div>')
    html.append('</div>')
    return "".join(html)


def _auto_analysis(top_scores: list[Mapping], buy_evidence: list[Mapping], sell_evidence: list[Mapping], political: list[Mapping], price_by_ticker: dict[str, float]) -> str:
    buy_scores = sorted(
        [x for x in top_scores if _safe_float(x.get("buy_amount")) > 0],
        key=lambda x: _safe_float(x.get("buy_amount")),
        reverse=True,
    )
    sell_scores = sorted(
        [x for x in top_scores if _safe_float(x.get("sell_amount")) > 0],
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
            lines.append(f"- {x.get('ticker')}: 去重后买入金额约 {_money(x.get('buy_amount'))}，原始买入记录 {x.get('buy_count', 0)} 笔，独立买入事件 {x.get('unique_buy_events', 0)} 起，净信号为 {x.get('signal_label')}。")
    else:
        lines.append("- 未发现可评分的 P/BUY 主动买入信号。")
    lines.append("")
    lines.append("2. 减持/卖出预警：")
    if sell_scores:
        for x in sell_scores[:8]:
            lines.append(f"- {x.get('ticker')}: 去重后卖出金额约 {_money(x.get('sell_amount'))}，卖出记录 {x.get('sell_count', 0)} 笔，独立卖出事件 {x.get('unique_sell_events', 0)} 起。")
    else:
        lines.append("- 未发现可评分的 S/SELL 减持信号。")
    lines.append("")
    lines.append("3. 明细校验：")
    if buy_evidence:
        top = sorted(buy_evidence, key=lambda t: _trade_amount_for_display(t, price_by_ticker)[0], reverse=True)[0]
        lines.append(f"- 最大主动买入明细：{top.get('ticker')} / {top.get('whale_name')} / {_trade_amount_for_display(top, price_by_ticker)[1]}。")
    if sell_evidence:
        top = sorted(sell_evidence, key=lambda t: _trade_amount_for_display(t, price_by_ticker)[0], reverse=True)[0]
        lines.append(f"- 最大卖出明细：{top.get('ticker')} / {top.get('whale_name')} / {_trade_amount_for_display(top, price_by_ticker)[1]}。")
    if political:
        p = sorted(political, key=lambda t: _trade_amount_for_display(t, price_by_ticker)[0], reverse=True)[0]
        lines.append(f"- 最大政界披露明细：{p.get('ticker')} / {p.get('whale_name')} / {p.get('action')} / {_trade_amount_for_display(p, price_by_ticker)[1]}。")
    lines.append("")
    lines.append("4. 风险提示：共同报告人、期权名义金额、基金会/信托长期减持可能放大表观金额。V12 已对共同报告人做经济金额去重，并对政界期权/股数披露使用估算标记，但关键记录仍建议点开原始披露人工复核。")
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
    trump_oge_trades: list[Mapping] | None = None,
    oge_executive_trades: list[Mapping] | None = None,
    oge_summary: list[Mapping] | None = None,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    price_by_ticker = _market_price_map(market_context)

    # V12: BUY Top Signals means “has active BUY amount”, even when net signal is
    # sell/neutral.  This prevents large buys such as Elon Musk/TSLA from being
    # hidden simply because the same stock also has many SELL rows.
    buy_scores = [x for x in top_scores if _safe_float(x.get("buy_amount")) > 0 or str(x.get("signal_label", "")).startswith("多头")]
    sell_scores = [x for x in top_scores if str(x.get("signal_label", "")).startswith("减持") or _safe_float(x.get("sell_amount")) > 0]

    core_buy_trades = core_buy_trades or [t for t in recent_trades if str(t.get("action") or "") == "BUY" and not _is_political_trade(t)]
    core_sell_trades = core_sell_trades or [t for t in recent_trades if str(t.get("action") or "") == "SELL" and not _is_political_trade(t)]
    political_recent_trades = [t for t in recent_trades if _is_political_trade(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}]
    buy_evidence = buy_evidence or []
    sell_evidence = sell_evidence or []
    noncore_trades = noncore_trades or []
    trump_oge_trades = trump_oge_trades or []
    oge_executive_trades = oge_executive_trades or []
    oge_summary = oge_summary or []

    if new_trade_count == 0:
        summary = "本次扫描未发现新的披露记录。邮件不重复列出历史内容；下方如有表格，是数据库中最近留存记录。"
    else:
        summary = f"本次扫描新增 {new_trade_count} 条披露交易记录。"

    ai_text = str(ai_analysis or "").strip()
    if not ai_text or ai_text in {"Gemini 没有返回分析内容。", "未启用。"}:
        ai_text = _auto_analysis(top_scores, buy_evidence, sell_evidence, political_recent_trades, price_by_ticker)

    buy_chart = _chart_rows(buy_evidence or core_buy_trades, price_by_ticker, actions={"BUY"}, top_tickers=10)
    sell_chart = _chart_rows(sell_evidence or core_sell_trades, price_by_ticker, actions={"SELL"}, top_tickers=10)
    political_chart = _chart_rows(political_recent_trades, price_by_ticker, actions={"BUY", "SELL"}, top_tickers=12, buy_first=True)
    trump_oge_chart = _chart_rows(trump_oge_trades, price_by_ticker, actions={"BUY", "SELL", "EXCHANGE"}, top_tickers=12, buy_first=True)
    cabinet_oge_chart = _chart_rows([t for t in oge_executive_trades if str(t.get("source") or "") != "OGE_EXECUTIVE_TRUMP"], price_by_ticker, actions={"BUY", "SELL", "EXCHANGE"}, top_tickers=12, buy_first=True)

    buy_table = _table(['股票', '净信号', '去重买入金额', '原始买入笔数', '去重经济笔数', '独立买入事件', '机会分', '共识分', '风险分', '解释'], _score_rows(buy_scores, "BUY")) if buy_scores else '<p>暂无主动买入类可评分信号。</p>'
    sell_table = _table(['股票', '信号', '去重卖出金额', '原始卖出笔数', '去重经济笔数', '独立卖出事件', '机会分', '共识分', '风险分', '解释'], _score_rows(sell_scores, "SELL")) if sell_scores else '<p>暂无减持/卖出类可评分信号。</p>'
    buy_evidence_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(buy_evidence, limit=100, price_by_ticker=price_by_ticker)) if buy_evidence else '<p>暂无可展示的主动买入明细。</p>'
    sell_evidence_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(sell_evidence, limit=100, price_by_ticker=price_by_ticker)) if sell_evidence else '<p>暂无可展示的减持/卖出明细。</p>'
    core_buy_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_buy_trades, limit=100, price_by_ticker=price_by_ticker)) if core_buy_trades else '<p>暂无近期核心 BUY 交易记录。</p>'
    core_sell_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(core_sell_trades, limit=120, price_by_ticker=price_by_ticker)) if core_sell_trades else '<p>暂无近期核心 SELL 交易记录。</p>'
    noncore_table = _table(['披露日', '交易日', '股票', '方向', '代码', '巨鲸', '角色', '估算金额', '来源'], _trade_rows(noncore_trades, limit=80, price_by_ticker=price_by_ticker)) if noncore_trades else '<p>暂无近期非主动/期权/授予类披露记录。</p>'
    political_trade_table = _table(['披露日', '交易日', '股票', '方向', '代码', '政界巨鲸', '机构/角色', '估算金额', '来源'], _political_trade_rows(political_recent_trades, price_by_ticker=price_by_ticker)) if political_recent_trades else '<p>暂无近期政界巨鲸 BUY/SELL 交易记录。</p>'
    political_summary_table = _table(['动作', '记录数', '涉及标的数', '入库金额合计'], _political_summary_rows(political_summary or [])) if political_summary else '<p>暂无政界交易诊断汇总。</p>'
    trump_oge_overview = _table(['动作', '记录数', '涉及标的数', '区间中点金额合计'], _trump_overview_rows(trump_oge_trades, price_by_ticker)) if trump_oge_trades else '<p>暂无特朗普 OGE 278-T 交易记录。请在 OGE_TRUMP_REPORT_URLS 配置官方 PDF URL。</p>'
    trump_oge_table = _table(['披露日', '交易日', '股票', '方向', '代码', '披露人', '角色', 'OGE金额区间/中点', '来源'], _trade_rows(trump_oge_trades, limit=160, source_label='OGE', price_by_ticker=price_by_ticker, buy_first=True)) if trump_oge_trades else '<p>暂无特朗普 OGE 278-T 明细。</p>'
    cabinet_trades = [t for t in oge_executive_trades if str(t.get("source") or "") != "OGE_EXECUTIVE_TRUMP"]
    cabinet_oge_table = _table(['披露日', '交易日', '股票', '方向', '代码', '披露人/部长', '角色', 'OGE金额区间/中点', '来源'], _trade_rows(cabinet_trades, limit=160, source_label='OGE', price_by_ticker=price_by_ticker, buy_first=True)) if cabinet_trades else '<p>暂无已配置/已解析的部长或 Cabinet-level OGE 278-T 交易记录。</p>'
    oge_summary_table = _table(['披露人', '角色', '动作', '记录数', '涉及标的数', '区间中点金额合计'], _oge_action_summary_rows(oge_summary)) if oge_summary else '<p>暂无 OGE 行政分支交易汇总。</p>'
    processed_names = {str(t.get("whale_name") or "") for t in oge_executive_trades}
    oge_watchlist_table = _table(['关注对象/职位', '状态'], _oge_watchlist_rows(processed_names))
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
h3 {{ margin: 16px 0 8px; }}
.badge {{ display: inline-block; padding: 3px 8px; background: #eef2ff; border-radius: 12px; }}
.notice {{ background: #fff7ed; padding: 12px; border-left: 4px solid #f97316; }}
.note {{ background: #f9fafb; padding: 10px; border-left: 4px solid #9ca3af; color: #374151; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 7px; vertical-align: top; }}
th {{ background: #f9fafb; text-align: left; }}
.small {{ color: #6b7280; font-size: 12px; }}
.chart {{ border: 1px solid #e5e7eb; background: #fff; padding: 10px; margin: 10px 0 18px; }}
.chart-group {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #e5e7eb; }}
.chart-title {{ margin-bottom: 5px; }}
.bar-row {{ display: grid; grid-template-columns: 230px 1fr 90px; gap: 8px; align-items: center; margin: 4px 0; font-size: 12px; }}
.bar-track {{ background: #f3f4f6; height: 12px; border-radius: 6px; overflow: hidden; }}
.bar {{ height: 12px; border-radius: 6px; }}
.bar.buy {{ background: #2563eb; }}
.bar.sell {{ background: #dc2626; }}
.bar.other {{ background: #6b7280; }}
.bar-value {{ text-align: right; color: #374151; }}
</style>
</head>
<body>
<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>
<p class="small">生成时间：{escape(now)}</p>
<p class="notice">{escape(summary)}</p>
<p><b>重要说明：</b>本报告是基于公开披露文件的研究筛选结果，不构成个性化投资建议。Form 4 和其他披露存在时间滞后、交易目的复杂、自动交易计划等限制。</p>
<p class="note">V13 报告新增 OGE 行政分支模块：特朗普 OGE 278-T 专题、部长/Cabinet 披露雷达、OGE 金额区间中点排序，以及共同报告人去重、同股票集中展示和离线 HTML 图表。Top Signals 是按 {escape(str(settings.lookback_days))} 天窗口聚合后的评分；明细表按“股票总金额优先、同股票内金额降序”展示。核心 BUY 只统计 P/BUY，核心 SELL 只统计 S/SELL；M/A/F/G/J 等非主动记录单独列入审计表。</p>

<h2>Gemini 综合分析</h2>
<pre style="white-space: pre-wrap; background:#f9fafb; padding:12px; border:1px solid #e5e7eb;">{escape(ai_text)}</pre>

<h2>总统特朗普 OGE 投资披露专题</h2>
<p class="note">本专题只展示已配置并成功解析的 OGE Form 278-T / 公开财务披露 PDF。为避免误读，报告表述为“特朗普披露账户发生的交易”；若 PDF 文本显示 discretionary / managed account / trust，则不应理解为本人亲自下单。OGE 金额为区间披露，图表和排序使用区间中点。</p>
{_oge_notice(trump_oge_trades)}
<h3>特朗普 OGE 交易概览</h3>
{trump_oge_overview}
<h3>特朗普 OGE 买卖图（股票 × 披露账户）</h3>
{trump_oge_chart}
<h3>特朗普 OGE 明细（BUY 优先，同股票集中）</h3>
{trump_oge_table}

<h2>部长 / Cabinet OGE 披露雷达</h2>
<p class="note">部长、Cabinet-level 官员和重点监管岗位的 278-T/278e 属于行政分支 OGE 披露体系。并非每位官员每月都有 278-T；无可报告交易时通常不会有“零交易”278-T。若要自动入库，需要把官方 PDF URL 配置到 OGE_CABINET_REPORTS。</p>
<h3>Cabinet / 高敏感岗位关注清单</h3>
{oge_watchlist_table}
<h3>已解析 Cabinet OGE 买卖图</h3>
{cabinet_oge_chart}
<h3>已解析 Cabinet OGE 明细</h3>
{cabinet_oge_table}
<h3>OGE 行政分支交易汇总</h3>
{oge_summary_table}

<h2>主动买入概览图（股票 × 巨鲸，按金额）</h2>
{buy_chart}

<h2>主动买入 Top Signals（按去重买入金额）</h2>
{buy_table}

<h2>主动买入明细佐证（同股票集中，按金额）</h2>
{buy_evidence_table}

<h2>减持/卖出概览图（股票 × 巨鲸，按金额）</h2>
{sell_chart}

<h2>减持/卖出预警 Top Signals（按去重卖出金额）</h2>
{sell_table}

<h2>减持/卖出明细佐证（同股票集中，按金额）</h2>
{sell_evidence_table}

<h2>政界交易 BUY/SELL 对比图（股票 × 政界巨鲸）</h2>
{political_chart}

<h2>政界巨鲸 BUY/SELL 披露（BUY 优先，同股票集中）</h2>
{political_trade_table}

<h2>政界交易诊断汇总</h2>
{political_summary_table}
<p class="small">注：政界 House PDF 的金额字段可能是披露区间、股数、期权合约数或 OCR 片段。V13 在图表和明细中对股票股数/期权合约尝试估算并标记“估算/名义”；OGE 278-T 使用披露区间中点，但入库金额汇总仍保留原始解析值，避免把估算值误当正式披露金额。</p>

<h2>行情 / 基本面 / 新闻情绪补充</h2>
{market_table}

<h2>近期核心 BUY 披露（{escape(str(settings.lookback_days))} 天，同股票集中，按金额）</h2>
{core_buy_table}

<h2>近期核心 SELL 披露（{escape(str(settings.lookback_days))} 天，同股票集中，按金额）</h2>
{core_sell_table}

<h2>近期非主动 / 期权 / 授予 / 税务披露（审计，不计入主动 BUY）</h2>
{noncore_table}

<h2>评分口径</h2>
<p>V13 同时识别 SEC Form 4 公司内部人交易、House 政界披露和 OGE 行政分支披露，并用 Alpha Vantage / Finnhub 免费接口补充行情、趋势、估值、基本面、新闻情绪与独立 insider 数据校验。机会分仍以公开披露交易为主；行情/基本面/情绪只做小幅透明调整。共同报告人同一经济交易会进行金额去重，但原始报告人仍保留在明细中供审计。本报告不构成个性化投资建议。</p>
</body>
</html>
"""
    return html


def save_report(html: str) -> Path:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"gemini_whale_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    return path
