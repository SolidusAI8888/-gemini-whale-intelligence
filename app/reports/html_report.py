from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
import json
import re
from typing import Iterable, Mapping

from app.config import settings


TRUMP_HIGHLIGHT_RE = re.compile(r"(Donald\s+J\.\s+Trump|Donald\s+Trump|Trump|特朗普)", re.I)
PELOSI_HIGHLIGHT_RE = re.compile(r"(Nancy\s+Pelosi|Pelosi|佩洛西)", re.I)


def _money(value) -> str:
    try:
        value = float(value or 0)
    except Exception:  # noqa: BLE001
        return "-"
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value >= 1_000_000_000:
        return f"{sign}${value/1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"{sign}${value/1_000_000:.2f}M"
    if value >= 1_000:
        return f"{sign}${value/1_000:.1f}K"
    return f"{sign}${value:.0f}"


def _safe_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:  # noqa: BLE001
        return 0.0


def _table(headers: list[str], rows: Iterable[list[str]], empty: str = "暂无数据。") -> str:
    rows = list(rows)
    if not rows:
        return f"<p>{escape(empty)}</p>"
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _raw_json_obj(t: Mapping) -> dict:
    raw = str(t.get("raw_json") or "")
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _raw_json_text(t: Mapping) -> str:
    obj = _raw_json_obj(t)
    if obj:
        return " ".join(str(obj.get(k) or "") for k in ["line", "context", "parser_block", "asset_name", "description"])
    return str(t.get("raw_json") or "")


def _market_price_map(market_context: list[Mapping] | None) -> dict[str, float]:
    prices: dict[str, float] = {}
    for row in market_context or []:
        ticker = str(row.get("ticker") or "").upper()
        price = _safe_float(row.get("price"))
        if ticker and price > 0:
            prices[ticker] = price
    return prices


def _is_political_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("POLITICAL") or category.startswith("Political")


def _is_oge_trade(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    category = str(t.get("whale_category") or "")
    return source.startswith("OGE_EXECUTIVE") or category.startswith("Executive:")


def _is_political_or_oge(t: Mapping) -> bool:
    return _is_political_trade(t) or _is_oge_trade(t)


def _trade_date_ok(t: Mapping) -> bool:
    start = str(getattr(settings, "scan_start_date", "2026-01-01") or "2026-01-01")
    d = str(t.get("trade_date") or t.get("filing_date") or "")[:10]
    return (not d) or d >= start


def _dedup_key(row: Mapping) -> tuple[str, ...]:
    return (
        str(row.get("ticker") or "").upper(),
        str(row.get("action") or "").upper(),
        str(row.get("transaction_code") or ""),
        str(row.get("trade_date") or ""),
        str(row.get("filing_date") or ""),
        str(row.get("accession_number") or row.get("filing_url") or row.get("source_id") or ""),
        f"{_safe_float(row.get('amount_usd')):.4f}",
        f"{_safe_float(row.get('shares')):.4f}",
        f"{_safe_float(row.get('price')):.4f}",
        str(row.get("source") or ""),
    )


def _dedup_economic_trades(trades: list[Mapping]) -> list[dict]:
    seen: dict[tuple[str, ...], dict] = {}
    for t in trades:
        key = _dedup_key(t)
        if key not in seen:
            row = dict(t)
            row["_joint_reporters"] = [str(t.get("whale_name") or "")] if t.get("whale_name") else []
            seen[key] = row
        else:
            name = str(t.get("whale_name") or "")
            if name and name not in seen[key]["_joint_reporters"]:
                seen[key]["_joint_reporters"].append(name)
    for row in seen.values():
        names = [n for n in row.get("_joint_reporters", []) if n]
        row["_display_whale_name"] = ", ".join(names[:3]) + (f" 等{len(names)}方" if len(names) > 3 else "") if names else str(row.get("whale_name") or "")
    return list(seen.values())


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
    """Return sortable amount, display text, note.

    V18 rule: political option ranking uses the official disclosed range/midpoint
    when available.  Option notional is shown only as an exposure note, not mixed
    into ordinary cash transaction totals.
    """
    base = _safe_float(t.get("amount_usd"))
    if _is_oge_trade(t):
        obj = _raw_json_obj(t)
        label = str(obj.get("amount_range_label") or "").strip()
        notes = []
        if obj.get("discretionary_account_flag"):
            notes.append("discretionary/managed")
        if obj.get("late_fee_flag"):
            notes.append("late fee")
        return base, (f"{label} 中点{_money(base)}" if label else _money(base)), "；".join(notes)

    if _is_political_trade(t):
        text = _raw_json_text(t).lower()
        contracts = _extract_int(r"(\d[\d,]*)\s+(?:call|put)\s+options?", text)
        strike = _extract_float(r"strike(?: price)?(?: of)?\s*\$?([\d,.]+)", text)
        note = ""
        if contracts and strike:
            notional = contracts * 100 * strike
            note = f"期权名义≈{_money(notional)}；排序用披露区间"
        elif "option" in text or "strike" in text:
            note = "期权交易；排序用披露区间"
        return base, _money(base), note

    return base, _money(base), ""


def _format_amount_cell(t: Mapping, price_by_ticker: dict[str, float]) -> str:
    _, amount, note = _trade_amount_for_display(t, price_by_ticker)
    html = escape(amount)
    if note:
        html += f'<br><span class="small">{escape(note)}</span>'
    return html


def _source_link(t: Mapping) -> str:
    src = escape(str(t.get("source") or ""))
    url = str(t.get("filing_url") or "")
    return f'<a href="{escape(url)}">{src}</a>' if url else src


def _latest_dates(rows: list[Mapping]) -> str:
    dates = sorted({str(r.get("trade_date") or "")[:10] for r in rows if r.get("trade_date")}, reverse=True)
    return ", ".join(dates[:3]) if dates else "-"


def _whales_for(rows: list[Mapping], price_by_ticker: dict[str, float], limit: int = 3) -> str:
    by_name: dict[str, float] = defaultdict(float)
    for r in rows:
        name = str(r.get("_display_whale_name") or r.get("whale_name") or "Unknown")
        by_name[name] += _trade_amount_for_display(r, price_by_ticker)[0]
    names = [name for name, _ in sorted(by_name.items(), key=lambda kv: kv[1], reverse=True)[:limit]]
    return ", ".join(names) if names else "-"


def _aggregate_by_ticker(trades: list[Mapping], price_by_ticker: dict[str, float]) -> list[dict]:
    groups: dict[str, dict] = {}
    for t in _dedup_economic_trades([x for x in trades if _trade_date_ok(x)]):
        ticker = str(t.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        action = str(t.get("action") or "").upper()
        if action not in {"BUY", "SELL", "EXCHANGE"}:
            continue
        g = groups.setdefault(ticker, {"ticker": ticker, "BUY": [], "SELL": [], "EXCHANGE": []})
        g[action].append(t)
    out = []
    for ticker, g in groups.items():
        buy_amt = sum(_trade_amount_for_display(x, price_by_ticker)[0] for x in g["BUY"])
        sell_amt = sum(_trade_amount_for_display(x, price_by_ticker)[0] for x in g["SELL"])
        exch_amt = sum(_trade_amount_for_display(x, price_by_ticker)[0] for x in g["EXCHANGE"])
        out.append({**g, "buy_amount": buy_amt, "sell_amount": sell_amt, "exchange_amount": exch_amt, "total": buy_amt + sell_amt + exch_amt})
    return sorted(out, key=lambda x: x["total"], reverse=True)


def _ticker_comparison_chart(trades: list[Mapping], price_by_ticker: dict[str, float], top_tickers: int = 10) -> str:
    agg = _aggregate_by_ticker(trades, price_by_ticker)[:top_tickers]
    if not agg:
        return "<p>暂无可绘制图表的数据。</p>"
    max_amt = max([max(x["buy_amount"], x["sell_amount"], x["exchange_amount"]) for x in agg] + [1.0])
    html = ['<div class="chart">']
    for item in agg:
        ticker = item["ticker"]
        html.append(f'<div class="chart-group"><div class="chart-title"><b>{escape(ticker)}</b> <span class="small">BUY {escape(_money(item["buy_amount"]))} / SELL {escape(_money(item["sell_amount"]))}</span></div>')
        for action, cls, rows, amount in [
            ("BUY", "buy", item["BUY"], item["buy_amount"]),
            ("SELL", "sell", item["SELL"], item["sell_amount"]),
            ("EXCHANGE", "other", item["EXCHANGE"], item["exchange_amount"]),
        ]:
            if amount <= 0:
                continue
            width = max(2, min(100, amount / max_amt * 100))
            label = f'{action} · {_whales_for(rows, price_by_ticker, limit=2)} · {_latest_dates(rows)}'
            html.append(f'<div class="bar-row"><div class="bar-label">{escape(label[:80])}</div><div class="bar-track"><div class="bar {cls}" style="width:{width:.1f}%"></div></div><div class="bar-value">{escape(_money(amount))}</div></div>')
        html.append('</div>')
    html.append('</div>')
    return "".join(html)


def _action_summary_table(trades: list[Mapping], price_by_ticker: dict[str, float], limit: int = 12) -> str:
    rows = []
    for item in _aggregate_by_ticker(trades, price_by_ticker)[:limit]:
        rows.append([
            f"<b>{escape(item['ticker'])}</b>",
            _money(item["buy_amount"]),
            escape(_whales_for(item["BUY"], price_by_ticker)),
            escape(_latest_dates(item["BUY"])),
            _money(item["sell_amount"]),
            escape(_whales_for(item["SELL"], price_by_ticker)),
            escape(_latest_dates(item["SELL"])),
            _money(item["buy_amount"] - item["sell_amount"]),
        ])
    return _table(["股票", "BUY金额", "主要买入巨鲸", "买入日期", "SELL金额", "主要卖出巨鲸", "卖出日期", "净额"], rows)


def _top_conclusion_rows(business: list[Mapping], political: list[Mapping], price_by_ticker: dict[str, float], limit: int = 8) -> list[list[str]]:
    combined = []
    for source_label, trades in [("商界", business), ("政界", political)]:
        for item in _aggregate_by_ticker(trades, price_by_ticker):
            buy = item["buy_amount"]
            sell = item["sell_amount"]
            if buy <= 0 and sell <= 0:
                continue
            direction = "BUY" if buy >= sell else "SELL"
            rows = item[direction]
            combined.append((max(buy, sell), source_label, item, direction, rows))
    combined.sort(key=lambda x: x[0], reverse=True)
    out = []
    for amount, source_label, item, direction, rows in combined[:limit]:
        opposite = item["sell_amount"] if direction == "BUY" else item["buy_amount"]
        out.append([
            escape(source_label),
            f"<b>{escape(item['ticker'])}</b>",
            escape(direction),
            _money(amount),
            _money(opposite),
            escape(_whales_for(rows, price_by_ticker, limit=3)),
            escape(_latest_dates(rows)),
            escape("新增/变化"),
        ])
    return out


def _detail_rows(trades: list[Mapping], price_by_ticker: dict[str, float], limit: int = 80) -> list[list[str]]:
    ordered = sorted(_dedup_economic_trades([x for x in trades if _trade_date_ok(x)]), key=lambda t: (_trade_amount_for_display(t, price_by_ticker)[0], str(t.get("trade_date") or "")), reverse=True)
    rows = []
    for t in ordered[:limit]:
        obj = _raw_json_obj(t)
        desc = str(obj.get("asset_name") or obj.get("description") or t.get("company_name") or "")
        rows.append([
            escape(str(t.get("trade_date") or "")),
            f"<b>{escape(str(t.get('ticker') or ''))}</b>",
            escape(str(t.get("action") or "")),
            escape(str(t.get("transaction_code") or "")),
            escape(str(t.get("_display_whale_name") or t.get("whale_name") or "")),
            escape(str(t.get("insider_role") or t.get("whale_category") or "")),
            _format_amount_cell(t, price_by_ticker),
            escape(desc[:120]),
            _source_link(t),
        ])
    return rows


def _executive_asset_rows(oge_trades: list[Mapping], price_by_ticker: dict[str, float], limit: int = 30) -> list[list[str]]:
    rows = []
    ordered = sorted(_dedup_economic_trades([x for x in oge_trades if _trade_date_ok(x)]), key=lambda t: (_trade_amount_for_display(t, price_by_ticker)[0], str(t.get("trade_date") or "")), reverse=True)
    for t in ordered[:limit]:
        obj = _raw_json_obj(t)
        asset = str(obj.get("asset_name") or t.get("company_name") or t.get("ticker") or "")
        doc_type = str(obj.get("report_type") or "278-T")
        rows.append([
            escape(str(t.get("whale_name") or "")),
            escape(str(t.get("insider_role") or "")),
            escape(doc_type),
            escape(asset[:140]),
            escape(str(t.get("action") or "")),
            _format_amount_cell(t, price_by_ticker),
            escape(str(t.get("trade_date") or "")),
            _source_link(t),
        ])
    return rows


def _highlight_names_in_text(text: str) -> str:
    if not text:
        return text
    text = TRUMP_HIGHLIGHT_RE.sub(lambda m: f'<span class="trump-highlight">{m.group(0)}</span>', text)
    text = PELOSI_HIGHLIGHT_RE.sub(lambda m: f'<span class="pelosi-highlight">{m.group(0)}</span>', text)
    return text


def _highlight_names_in_html(html: str) -> str:
    if not html:
        return html
    m = re.search(r"(<body[^>]*>)", html, re.I)
    if not m:
        return html
    head = html[: m.end()]
    body = html[m.end():]
    end = re.search(r"</body>", body, re.I)
    body_inner, tail = (body[: end.start()], body[end.start():]) if end else (body, "")
    protected_blocks: list[str] = []

    def protect(match: re.Match) -> str:
        protected_blocks.append(match.group(0))
        return f"@@NAME_PROTECTED_{len(protected_blocks)-1}@@"

    protected = re.sub(r"<(script|style|textarea|code)\b[^>]*>.*?</\1>", protect, body_inner, flags=re.I | re.S)
    parts = re.split(r"(<[^>]+>)", protected)
    for idx, part in enumerate(parts):
        if part and not part.startswith("<"):
            parts[idx] = _highlight_names_in_text(part)
    highlighted = "".join(parts)
    for idx, block in enumerate(protected_blocks):
        highlighted = highlighted.replace(f"@@NAME_PROTECTED_{idx}@@", block)
    return head + highlighted + tail


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
    buy_evidence = buy_evidence or []
    sell_evidence = sell_evidence or []
    core_buy_trades = core_buy_trades or []
    core_sell_trades = core_sell_trades or []
    oge_executive_trades = oge_executive_trades or []

    all_recent = [t for t in recent_trades if _trade_date_ok(t)]
    political_trades = [t for t in all_recent if _is_political_or_oge(t)] + [t for t in oge_executive_trades if _trade_date_ok(t)]
    # Trump is now handled as a normal political/executive whale, not a separate chapter.
    business_trades = [t for t in (core_buy_trades + core_sell_trades + buy_evidence + sell_evidence) if _trade_date_ok(t) and not _is_political_or_oge(t)]

    # If caller did not provide evidence tables, fall back to recent non-political records.
    if not business_trades:
        business_trades = [t for t in all_recent if not _is_political_or_oge(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}]

    change_class = "big-change" if new_trade_count > 0 else "no-change"
    change_text = f"今日新增/变化披露记录：{new_trade_count} 条" if new_trade_count > 0 else "今日无新增重大变化"

    top_conclusions = _table(
        ["类别", "股票", "方向", "金额", "反向金额", "主要巨鲸", "交易日期", "变化"],
        _top_conclusion_rows(business_trades, political_trades, price_by_ticker, limit=10),
        empty="暂无达到阈值的巨鲸行动。",
    )
    business_chart = _ticker_comparison_chart(business_trades, price_by_ticker, top_tickers=10)
    political_chart = _ticker_comparison_chart(political_trades, price_by_ticker, top_tickers=12)
    business_summary = _action_summary_table(business_trades, price_by_ticker, limit=15)
    political_summary_table = _action_summary_table(political_trades, price_by_ticker, limit=18)
    business_details = _table(["交易日", "股票", "方向", "代码", "巨鲸", "角色", "金额", "标的说明", "来源"], _detail_rows(business_trades, price_by_ticker, limit=60))
    political_details = _table(["交易日", "股票/标的", "方向", "代码", "政界巨鲸", "角色", "金额", "标的说明", "来源"], _detail_rows(political_trades, price_by_ticker, limit=80))
    executive_assets = _table(["人物", "职位", "披露类型", "投资标的/描述", "动作", "金额/估值区间", "交易/披露日期", "来源"], _executive_asset_rows(oge_executive_trades, price_by_ticker, limit=40))

    html = f"""
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<title>Gemini-美股聪明钱_政商巨鲸行动追踪</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif; line-height: 1.55; color: #111827; max-width: 1280px; margin: 0 auto; padding: 18px; }}
h1 {{ color: #111827; }}
h2 {{ margin-top: 28px; border-top: 1px solid #e5e7eb; padding-top: 18px; }}
h3 {{ margin: 16px 0 8px; }}
.notice {{ background: #fff7ed; padding: 12px; border-left: 4px solid #f97316; }}
.note {{ background: #f9fafb; padding: 10px; border-left: 4px solid #9ca3af; color: #374151; }}
.big-change {{ font-size: 24px; font-weight: 800; background: #fef3c7; border: 2px solid #f59e0b; padding: 14px; border-radius: 8px; }}
.no-change {{ font-size: 24px; font-weight: 800; background: #ecfdf5; border: 2px solid #10b981; padding: 14px; border-radius: 8px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 7px; vertical-align: top; }}
th {{ background: #f9fafb; text-align: left; }}
.small {{ color: #6b7280; font-size: 12px; }}
.chart {{ border: 1px solid #e5e7eb; background: #fff; padding: 10px; margin: 10px 0 18px; }}
.chart-group {{ margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px dashed #e5e7eb; }}
.chart-title {{ margin-bottom: 5px; }}
.bar-row {{ display: grid; grid-template-columns: 320px 1fr 95px; gap: 8px; align-items: center; margin: 4px 0; font-size: 12px; }}
.bar-track {{ background: #f3f4f6; height: 12px; border-radius: 6px; overflow: hidden; }}
.bar {{ height: 12px; border-radius: 6px; }}
.bar.buy {{ background: #2563eb; }}
.bar.sell {{ background: #dc2626; }}
.bar.other {{ background: #6b7280; }}
.bar-value {{ text-align: right; color: #374151; }}
.trump-highlight {{ background: #fef08a; color: #78350f; font-weight: 700; padding: 0 2px; border-radius: 3px; }}
.pelosi-highlight {{ background: #fde68a; color: #7c2d12; font-weight: 700; padding: 0 2px; border-radius: 3px; }}
</style>
</head>
<body>
<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>
<p class="small">生成时间：{escape(now)}；交易时间范围：{escape(settings.scan_start_date)} 至今；正式报告目标发送时间：柏林时间每日 08:00。</p>
<div class="{change_class}">{escape(change_text)}</div>
<p class="notice"><b>报告定位：</b>快速了解近期商界/政界巨鲸在美股及公开投资标的上的真金白银 BUY/SELL 披露。金额来自公开披露，政治期权默认按披露金额区间排序，名义敞口只作备注；本报告不构成个性化投资建议。</p>

<h2>一、今日结论总览</h2>
<p class="note">本部分集中展示所有核心图示。图示以股票/标的为纲，同一股票的 BUY 与 SELL 放在同一图组中对比，旁边列出主要巨鲸和交易日期。</p>
<h3>关键行动 Top 摘要</h3>
{top_conclusions}
<h3>商界巨鲸 BUY/SELL 对比图（股票 × 巨鲸）</h3>
{business_chart}
<h3>政界巨鲸 BUY/SELL 对比图（股票/标的 × 政界巨鲸）</h3>
{political_chart}

<h2>二、商界巨鲸行动</h2>
<p class="note">仅展示核心摘要与必要明细。更长的审计明细建议另存附件，不放入正式邮件正文。</p>
<h3>商界巨鲸行动摘要</h3>
{business_summary}
<h3>商界巨鲸必要明细</h3>
{business_details}

<h2>三、政界巨鲸行动</h2>
<p class="note">Trump 作为政界巨鲸与 Pelosi、House/Senate、OGE 行政分支披露统一列示。Trump 与 Pelosi 名字保留高亮，便于快速阅读。</p>
<h3>政界巨鲸行动摘要</h3>
{political_summary_table}
<h3>政界巨鲸必要明细</h3>
{political_details}
<h3>行政分支关键人物投资标的雷达（不限美股）</h3>
<p class="small">该表基于当前已配置/已发现并可解析的 OGE 资料。278-T 表示交易型披露；278e/伦理协议等资产型披露如后续接入，应显示为持仓/资产而非近期交易。</p>
{executive_assets}

<h2>四、口径说明</h2>
<ul>
<li>扫描交易日期从 {escape(settings.scan_start_date)} 起，2025 年及以前交易不进入正式正文。</li>
<li>政治期权交易同时保留“披露金额区间”和“期权名义敞口”说明；排名默认使用披露金额区间，避免把期权名义金额与现金成交金额混排。</li>
<li>已删除正文中的关联 SELL 审计、行情/基本面/新闻情绪、非主动/税务/授予审计和超长 BUY/SELL 明细；如后续需要，可单独生成附件。</li>
<li>公开披露存在滞后、OCR/解析误差、共同报告人、10b5-1、信托/基金会、委托账户等因素，关键交易仍建议点击原始披露复核。</li>
</ul>
</body>
</html>
"""
    return _highlight_names_in_html(html)


def save_report(html: str) -> Path:
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    path = settings.report_dir / f"gemini_whale_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    path.write_text(html, encoding="utf-8")
    return path
