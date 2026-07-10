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


def _table(headers: list[str], rows: Iterable[list[str] | tuple[str, list[str]]], empty: str = "暂无数据。") -> str:
    rows = list(rows)
    if not rows:
        return f"<p>{escape(empty)}</p>"
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body_parts = []
    for row in rows:
        row_class = ""
        cells = row
        if isinstance(row, tuple) and len(row) == 2 and isinstance(row[0], str):
            row_class = row[0]
            cells = row[1]
        cls = f' class="{escape(row_class)}"' if row_class else ""
        body_parts.append(f"<tr{cls}>" + "".join(f"<td>{cell}</td>" for cell in cells) + "</tr>")
    body = "".join(body_parts)
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


def _is_oge_asset(t: Mapping) -> bool:
    source = str(t.get("source") or "")
    action = str(t.get("action") or "").upper()
    raw = _raw_json_obj(t)
    doc = str(raw.get("report_type") or "")
    return source == "OGE_EXECUTIVE_ASSET" or action in {"HOLDING", "DISCLOSURE"} or doc.upper() in {"OGE_278E", "278E", "ETHICS", "DIVESTITURE"}


def _is_institutional_13f(t: Mapping) -> bool:
    return str(t.get("source") or "") == "INSTITUTIONAL_13F" or str(t.get("action") or "").upper() == "HOLDING_13F"


def _institutional_13f_amount_usd(t: Mapping) -> float:
    """Return a display-safe 13F market value in dollars.

    SEC 13F information-table ``value`` is reported in thousands of dollars.
    Older cached rows in this project may already have amount_usd inflated by
    another 1000x.  The report layer must therefore prefer the raw SEC value
    and normalize defensively, so a stale DB cache can never show trillion-scale
    active-manager single positions again.
    """
    current = _safe_float(t.get("amount_usd"))
    if not _is_institutional_13f(t):
        return current

    obj = _raw_json_obj(t)
    reported = obj.get("value_reported")
    if reported is None:
        reported = obj.get("value_thousands_usd")
    if reported is not None:
        try:
            reported_value = float(str(reported).replace(",", ""))
            unit = str(obj.get("value_unit") or "thousands_usd").lower()
            if unit in {"usd", "usd_normalized", "dollars"}:
                normalized = reported_value
            else:
                # SEC 13F XML <value> is normally in thousands of dollars, but
                # legacy cached rows may have written an already-normalized USD
                # value back into value_reported while still labeling it
                # thousands_usd. Convert once, then apply a strict display guard.
                normalized = reported_value * 1000.0
            while normalized > 100_000_000_000:
                normalized /= 1000.0
            return normalized
        except Exception:  # noqa: BLE001
            pass

    # Final presentation guard for legacy rows without raw_json.  A single
    # active-manager 13F line above $100B in this project has consistently been
    # the known 1000x bug, not a real holding.
    normalized = current
    while normalized > 100_000_000_000:
        normalized /= 1000.0
    return normalized


def _is_political_or_oge(t: Mapping) -> bool:
    return (_is_political_trade(t) or _is_oge_trade(t)) and not _is_institutional_13f(t)


def _valid_date_string(value: str) -> bool:
    try:
        d = datetime.fromisoformat(value[:10]).date()
    except Exception:  # noqa: BLE001
        return False
    today = datetime.now().date()
    start = datetime.fromisoformat(str(getattr(settings, "scan_start_date", "2026-01-01") or "2026-01-01")[:10]).date()
    return start <= d <= today


def _trade_date_ok(t: Mapping) -> bool:
    # OGE 278e/HOLDING and 13F rows are not real transaction rows; their date
    # fields represent report periods or disclosure dates and are handled in
    # separate sections.
    if _is_oge_asset(t) or _is_institutional_13f(t):
        d = str(t.get("filing_date") or t.get("trade_date") or "")[:10]
        return (not d) or d >= str(getattr(settings, "scan_start_date", "2026-01-01") or "2026-01-01")
    d = str(t.get("trade_date") or t.get("filing_date") or "")[:10]
    return (not d) or _valid_date_string(d)


def _is_new_trade(t: Mapping, new_since: str | None = None) -> bool:
    """Return whether this DB row was inserted during the current scan.

    V22 uses the persisted SQLite database restored by GitHub Actions cache.
    A row whose created_at timestamp is newer than the current run start is a
    true newly discovered disclosure, not merely a 2026-to-date historical row.
    """
    if not new_since:
        return False
    created_at = str(t.get("created_at") or "")[:19]
    return bool(created_at and created_at >= str(new_since)[:19])


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
            # Preserve the newest created_at among economically duplicate rows so
            # a daily-new duplicate is still highlighted in detail tables.
            existing_created = str(seen[key].get("created_at") or "")
            incoming_created = str(t.get("created_at") or "")
            if incoming_created and incoming_created > existing_created:
                seen[key]["created_at"] = incoming_created
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
    dates = sorted({str(r.get("trade_date") or "")[:10] for r in rows if r.get("trade_date") and _trade_date_ok(r)}, reverse=True)
    return ", ".join(dates[:3]) if dates else "-"


def _display_trade_date(t: Mapping) -> str:
    if _is_oge_asset(t):
        return "不适用"
    d = str(t.get("trade_date") or "")[:10]
    if d and _valid_date_string(d):
        return d
    return "日期待复核"


def _display_report_date(t: Mapping) -> str:
    obj = _raw_json_obj(t)
    return str(obj.get("report_period") or t.get("filing_date") or t.get("trade_date") or "")[:10] or "-"


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


def _top_conclusion_rows(business: list[Mapping], political: list[Mapping], price_by_ticker: dict[str, float], limit: int = 8, new_since: str | None = None) -> list[list[str]]:
    combined = []
    for source_label, trades in [("商界", business), ("政界", political)]:
        for item in _aggregate_by_ticker(trades, price_by_ticker):
            buy = item["buy_amount"]
            sell = item["sell_amount"]
            if buy <= 0 and sell <= 0:
                continue
            direction = "BUY" if buy >= sell else "SELL"
            rows = item[direction]
            is_new = any(_is_new_trade(r, new_since) for r in (item["BUY"] + item["SELL"] + item["EXCHANGE"]))
            combined.append((max(buy, sell), source_label, item, direction, rows, is_new))
    # New/changed rows are promoted first, then by amount. This keeps the first
    # screen focused on genuinely new daily discoveries.
    combined.sort(key=lambda x: (1 if x[5] else 0, x[0]), reverse=True)
    out = []
    for amount, source_label, item, direction, rows, is_new in combined[:limit]:
        opposite = item["sell_amount"] if direction == "BUY" else item["buy_amount"]
        change_html = '<span class="change-new">新增/变化</span>' if is_new else '<span class="change-existing">既有</span>'
        cells = [
            escape(source_label),
            f"<b>{escape(item['ticker'])}</b>",
            escape(direction),
            _money(amount),
            _money(opposite),
            escape(_whales_for(rows, price_by_ticker, limit=3)),
            escape(_latest_dates(rows)),
            change_html,
        ]
        out.append(("row-new", cells) if is_new else cells)
    return out


def _detail_rows(trades: list[Mapping], price_by_ticker: dict[str, float], limit: int = 80, new_since: str | None = None) -> list[list[str] | tuple[str, list[str]]]:
    ordered = sorted(
        _dedup_economic_trades([x for x in trades if _trade_date_ok(x) and not _is_oge_asset(x) and not _is_institutional_13f(x)]),
        # Keep the necessary-detail table sorted by economic importance.
        # Daily-new rows are highlighted in place; they are not promoted to the top.
        key=lambda t: (_trade_amount_for_display(t, price_by_ticker)[0], str(t.get("trade_date") or "")),
        reverse=True,
    )
    rows = []
    for t in ordered[:limit]:
        obj = _raw_json_obj(t)
        desc = str(obj.get("asset_name") or obj.get("description") or t.get("company_name") or "")
        cells = [
            escape(_display_trade_date(t)),
            f"<b>{escape(str(t.get('ticker') or ''))}</b>",
            escape(str(t.get("action") or "")),
            escape(str(t.get("transaction_code") or "")),
            escape(str(t.get("_display_whale_name") or t.get("whale_name") or "")),
            escape(str(t.get("insider_role") or t.get("whale_category") or "")),
            _format_amount_cell(t, price_by_ticker),
            escape(desc[:120]),
            _source_link(t),
        ]
        rows.append(("row-new", cells) if _is_new_trade(t, new_since) else cells)
    return rows


def _executive_asset_rows(oge_trades: list[Mapping], price_by_ticker: dict[str, float], limit: int = 30, new_since: str | None = None) -> list[list[str] | tuple[str, list[str]]]:
    rows = []
    asset_rows = [x for x in oge_trades if _is_oge_asset(x) and _trade_date_ok(x)]
    ordered = sorted(_dedup_economic_trades(asset_rows), key=lambda t: (_is_new_trade(t, new_since), str(t.get("filing_date") or t.get("trade_date") or ""), _trade_amount_for_display(t, price_by_ticker)[0]), reverse=True)
    for t in ordered[:limit]:
        obj = _raw_json_obj(t)
        asset = str(obj.get("asset_name") or obj.get("description") or t.get("company_name") or t.get("ticker") or "")
        doc_type = str(obj.get("report_type") or "OGE_278e/HOLDING")
        cells = [
            escape(str(t.get("whale_name") or "")),
            escape(str(t.get("insider_role") or "")),
            escape(doc_type),
            escape(asset[:140]),
            escape(str(t.get("action") or "")),
            _format_amount_cell(t, price_by_ticker),
            escape(_display_report_date(t)),
            _source_link(t),
        ]
        rows.append(("row-new", cells) if _is_new_trade(t, new_since) else cells)
    return rows


def _institutional_13f_rows(holdings: list[Mapping], limit: int = 60, new_since: str | None = None) -> list[list[str] | tuple[str, list[str]]]:
    # Keep each institution's holdings together.  Institutions are ordered by
    # their largest visible holding value; holdings inside each institution are
    # sorted by holding market value descending.
    groups: dict[str, list[Mapping]] = defaultdict(list)
    for h in holdings:
        if not _is_institutional_13f(h):
            continue
        obj = _raw_json_obj(h)
        manager = str(obj.get("manager") or h.get("insider_role") or h.get("whale_name") or "Unknown manager")
        groups[manager].append(h)

    ordered_groups = sorted(
        groups.items(),
        key=lambda kv: max((_institutional_13f_amount_usd(x) for x in kv[1]), default=0.0),
        reverse=True,
    )
    rows = []
    used = 0
    for manager, group_rows in ordered_groups:
        group_rows = sorted(group_rows, key=lambda h: _institutional_13f_amount_usd(h), reverse=True)
        first = True
        for h in group_rows:
            if used >= limit:
                return rows
            obj = _raw_json_obj(h)
            issuer = str(obj.get("nameOfIssuer") or h.get("company_name") or h.get("ticker") or "")
            lead = str(obj.get("lead_investor") or h.get("whale_name") or "")
            cells = [
                escape(manager if first else ""),
                escape(lead if first else ""),
                f"<b>{escape(str(h.get('ticker') or ''))}</b>",
                escape(issuer[:100]),
                _money(_institutional_13f_amount_usd(h)),
                escape(f"{_safe_float(h.get('shares')):,.0f}" if _safe_float(h.get("shares")) else "-"),
                escape(str(obj.get("report_period") or h.get("trade_date") or "")[:10]),
                escape(str(h.get("filing_date") or "")[:10]),
                _source_link(h),
            ]
            rows.append(("row-new", cells) if _is_new_trade(h, new_since) else cells)
            first = False
            used += 1
    return rows



def _institutional_13f_consensus_rows(holdings: list[Mapping], limit: int = 20) -> list[list[str]]:
    """Compare each watched manager's latest 13F with its prior 13F.

    The output is a consensus-style table: which issuers were increased by
    multiple top-20 institutional whales, and which were reduced or exited.
    It is a quarter-over-quarter 13F analysis, not a same-day trading signal.
    """
    by_manager_period: dict[str, dict[str, dict[str, Mapping]]] = defaultdict(lambda: defaultdict(dict))
    manager_lead: dict[str, str] = {}
    for h in holdings:
        if not _is_institutional_13f(h):
            continue
        obj = _raw_json_obj(h)
        manager = str(obj.get("manager") or h.get("insider_role") or h.get("whale_name") or "Unknown manager")
        lead = str(obj.get("lead_investor") or h.get("whale_name") or "")
        if lead:
            manager_lead[manager] = lead
        period = str(obj.get("report_period") or h.get("trade_date") or "")[:10]
        ticker = str(h.get("ticker") or "").upper().strip()
        if not period or not ticker:
            continue
        existing = by_manager_period[manager][period].get(ticker)
        if existing is None or _institutional_13f_amount_usd(h) > _institutional_13f_amount_usd(existing):
            by_manager_period[manager][period][ticker] = h

    consensus: dict[str, dict] = {}
    comparable_managers = 0
    for manager, periods in by_manager_period.items():
        ordered_periods = sorted(periods.keys(), reverse=True)
        if len(ordered_periods) < 2:
            continue
        comparable_managers += 1
        latest_p, prev_p = ordered_periods[0], ordered_periods[1]
        latest = periods[latest_p]
        prev = periods[prev_p]
        tickers = set(latest) | set(prev)
        display_manager = f"{manager} / {manager_lead.get(manager, '')}" if manager_lead.get(manager) and manager_lead.get(manager) not in manager else manager
        for ticker in tickers:
            latest_amt = _institutional_13f_amount_usd(latest.get(ticker, {})) if ticker in latest else 0.0
            prev_amt = _institutional_13f_amount_usd(prev.get(ticker, {})) if ticker in prev else 0.0
            delta = latest_amt - prev_amt
            if abs(delta) < 1000:
                continue
            item = consensus.setdefault(ticker, {
                "ticker": ticker,
                "issuer": "",
                "latest_total": 0.0,
                "prev_total": 0.0,
                "delta_total": 0.0,
                "increased": [],
                "reduced": [],
                "new": [],
                "exited": [],
                "periods": set(),
            })
            source_row = latest.get(ticker) or prev.get(ticker) or {}
            obj = _raw_json_obj(source_row)
            if not item["issuer"]:
                item["issuer"] = str(obj.get("nameOfIssuer") or source_row.get("company_name") or "")
            item["latest_total"] += latest_amt
            item["prev_total"] += prev_amt
            item["delta_total"] += delta
            item["periods"].add(f"{prev_p}→{latest_p}")
            if prev_amt <= 0 and latest_amt > 0:
                item["new"].append((display_manager, delta))
                item["increased"].append((display_manager, delta))
            elif latest_amt <= 0 and prev_amt > 0:
                item["exited"].append((display_manager, abs(delta)))
                item["reduced"].append((display_manager, abs(delta)))
            elif delta > 0:
                item["increased"].append((display_manager, delta))
            elif delta < 0:
                item["reduced"].append((display_manager, abs(delta)))

    scored = []
    for item in consensus.values():
        inc = len(item["increased"])
        dec = len(item["reduced"])
        if inc < 2 and dec < 2:
            continue
        if inc >= 2 and dec == 0:
            signal = "一致增持"
            score = (3, inc, abs(item["delta_total"]))
        elif dec >= 2 and inc == 0:
            signal = "一致减持/退出"
            score = (3, dec, abs(item["delta_total"]))
        elif inc > dec:
            signal = "多数增持"
            score = (2, inc - dec, abs(item["delta_total"]))
        elif dec > inc:
            signal = "多数减持"
            score = (2, dec - inc, abs(item["delta_total"]))
        else:
            signal = "分歧"
            score = (1, inc + dec, abs(item["delta_total"]))
        item["signal"] = signal
        scored.append((score, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    rows = []
    for _, item in scored[:limit]:
        inc_names = [name for name, _ in sorted(item["increased"], key=lambda kv: kv[1], reverse=True)[:6]]
        dec_names = [name for name, _ in sorted(item["reduced"], key=lambda kv: kv[1], reverse=True)[:6]]
        notes = []
        if item["new"]:
            notes.append(f"新建仓{len(item['new'])}家")
        if item["exited"]:
            notes.append(f"清仓/退出{len(item['exited'])}家")
        cells = [
            f"<b>{escape(item['ticker'])}</b>",
            escape(item["issuer"][:80] or "-"),
            escape(item["signal"]),
            escape(str(len(item["increased"]))),
            escape("；".join(inc_names) or "-"),
            escape(str(len(item["reduced"]))),
            escape("；".join(dec_names) or "-"),
            _money(item["delta_total"]),
            f"{_money(item['prev_total'])} → {_money(item['latest_total'])}",
            escape("；".join(sorted(item["periods"]))),
            escape("；".join(notes) or f"可比机构数：{comparable_managers}"),
        ]
        rows.append(cells)
    return rows

def _institutional_13f_consensus_table(holdings: list[Mapping], limit: int = 20) -> str:
    rows = _institutional_13f_consensus_rows(holdings, limit=limit)
    return _table(
        ["标的", "发行人", "共识信号", "增持家数", "增持机构", "减持家数", "减持机构", "合计变化", "上期→最新合计市值", "比较区间", "备注"],
        rows,
        empty="暂无足够的相邻两期 13F 数据。请将 INSTITUTIONAL_13F_FILINGS_PER_MANAGER 设为 2，并连续运行一次以采集最近两期 13F 后再查看共识增减持分析。",
    )



def _institutional_13f_manager_periods(holdings: list[Mapping]) -> tuple[dict[str, dict[str, dict[str, Mapping]]], dict[str, str]]:
    """Return manager -> report_period -> ticker -> holding rows for 13F analysis."""
    by_manager_period: dict[str, dict[str, dict[str, Mapping]]] = defaultdict(lambda: defaultdict(dict))
    manager_lead: dict[str, str] = {}
    for h in holdings:
        if not _is_institutional_13f(h):
            continue
        obj = _raw_json_obj(h)
        manager = str(obj.get("manager") or h.get("insider_role") or h.get("whale_name") or "Unknown manager")
        lead = str(obj.get("lead_investor") or h.get("whale_name") or "")
        if lead:
            manager_lead[manager] = lead
        period = str(obj.get("report_period") or h.get("trade_date") or "")[:10]
        ticker = str(h.get("ticker") or "").upper().strip()
        if not period or not ticker:
            continue
        existing = by_manager_period[manager][period].get(ticker)
        if existing is None or _institutional_13f_amount_usd(h) > _institutional_13f_amount_usd(existing):
            by_manager_period[manager][period][ticker] = h
    return by_manager_period, manager_lead


def _display_manager_name(manager: str, manager_lead: dict[str, str]) -> str:
    lead = manager_lead.get(manager, "")
    return f"{manager} / {lead}" if lead and lead not in manager else manager


def _issuer_from_13f_row(row: Mapping) -> str:
    obj = _raw_json_obj(row)
    return str(obj.get("nameOfIssuer") or row.get("company_name") or row.get("ticker") or "")


def _institutional_13f_current_concentration_rows(holdings: list[Mapping], limit: int = 5) -> list[list[str]]:
    """Top current holdings across the latest report for each top-20 manager."""
    by_manager_period, manager_lead = _institutional_13f_manager_periods(holdings)
    aggregate: dict[str, dict] = {}
    latest_total = 0.0
    comparable_managers = 0
    for manager, periods in by_manager_period.items():
        ordered_periods = sorted(periods.keys(), reverse=True)
        if not ordered_periods:
            continue
        comparable_managers += 1
        latest_p = ordered_periods[0]
        for ticker, h in periods[latest_p].items():
            amount = _institutional_13f_amount_usd(h)
            if amount <= 0:
                continue
            latest_total += amount
            item = aggregate.setdefault(ticker, {
                "ticker": ticker,
                "issuer": _issuer_from_13f_row(h),
                "amount": 0.0,
                "holders": [],
                "periods": set(),
            })
            if not item["issuer"]:
                item["issuer"] = _issuer_from_13f_row(h)
            item["amount"] += amount
            item["holders"].append((_display_manager_name(manager, manager_lead), amount))
            item["periods"].add(latest_p)
    rows = []
    for item in sorted(aggregate.values(), key=lambda x: x["amount"], reverse=True)[:limit]:
        holders = [name for name, _ in sorted(item["holders"], key=lambda kv: kv[1], reverse=True)[:6]]
        pct = f"{(item['amount'] / latest_total * 100):.1f}%" if latest_total > 0 else "-"
        rows.append([
            f"<b>{escape(item['ticker'])}</b>",
            escape(item["issuer"][:80] or "-"),
            _money(item["amount"]),
            escape(pct),
            escape(str(len(item["holders"]))),
            escape("；".join(holders) or "-"),
            escape("；".join(sorted(item["periods"])) or "-"),
            escape(f"基于{comparable_managers}家已采集最新期13F"),
        ])
    return rows


def _institutional_13f_delta_concentration_rows(holdings: list[Mapping], direction: str, limit: int = 5) -> list[list[str]]:
    """Top aggregate increases/new positions or reductions/exits between the latest two 13F periods."""
    by_manager_period, manager_lead = _institutional_13f_manager_periods(holdings)
    aggregate: dict[str, dict] = {}
    comparable_managers = 0
    for manager, periods in by_manager_period.items():
        ordered_periods = sorted(periods.keys(), reverse=True)
        if len(ordered_periods) < 2:
            continue
        comparable_managers += 1
        latest_p, prev_p = ordered_periods[0], ordered_periods[1]
        latest = periods[latest_p]
        prev = periods[prev_p]
        for ticker in set(latest) | set(prev):
            latest_row = latest.get(ticker)
            prev_row = prev.get(ticker)
            latest_amt = _institutional_13f_amount_usd(latest_row or {}) if latest_row else 0.0
            prev_amt = _institutional_13f_amount_usd(prev_row or {}) if prev_row else 0.0
            delta = latest_amt - prev_amt
            if abs(delta) < 1000:
                continue
            if direction == "increase" and delta <= 0:
                continue
            if direction == "decrease" and delta >= 0:
                continue
            source_row = latest_row or prev_row or {}
            item = aggregate.setdefault(ticker, {
                "ticker": ticker,
                "issuer": _issuer_from_13f_row(source_row),
                "delta_abs": 0.0,
                "latest_total": 0.0,
                "prev_total": 0.0,
                "managers": [],
                "new_count": 0,
                "exit_count": 0,
                "periods": set(),
            })
            if not item["issuer"]:
                item["issuer"] = _issuer_from_13f_row(source_row)
            item["delta_abs"] += abs(delta)
            item["latest_total"] += latest_amt
            item["prev_total"] += prev_amt
            if direction == "increase" and prev_amt <= 0 and latest_amt > 0:
                item["new_count"] += 1
            if direction == "decrease" and latest_amt <= 0 and prev_amt > 0:
                item["exit_count"] += 1
            item["managers"].append((_display_manager_name(manager, manager_lead), abs(delta)))
            item["periods"].add(f"{prev_p}→{latest_p}")
    total_abs = sum(item["delta_abs"] for item in aggregate.values())
    rows = []
    for item in sorted(aggregate.values(), key=lambda x: x["delta_abs"], reverse=True)[:limit]:
        managers = [name for name, _ in sorted(item["managers"], key=lambda kv: kv[1], reverse=True)[:6]]
        pct = f"{(item['delta_abs'] / total_abs * 100):.1f}%" if total_abs > 0 else "-"
        notes = []
        if direction == "increase" and item["new_count"]:
            notes.append(f"新建仓{item['new_count']}家")
        if direction == "decrease" and item["exit_count"]:
            notes.append(f"清仓/退出{item['exit_count']}家")
        notes.append(f"可比机构数：{comparable_managers}")
        rows.append([
            f"<b>{escape(item['ticker'])}</b>",
            escape(item["issuer"][:80] or "-"),
            _money(item["delta_abs"]),
            escape(pct),
            escape(str(len(item["managers"]))),
            escape("；".join(managers) or "-"),
            f"{_money(item['prev_total'])} → {_money(item['latest_total'])}",
            escape("；".join(sorted(item["periods"])) or "-"),
            escape("；".join(notes)),
        ])
    return rows


def _institutional_13f_current_concentration_table(holdings: list[Mapping], limit: int = 5) -> str:
    return _table(
        ["标的", "发行人", "合计13F市值", "占最新持仓样本", "持有机构数", "主要持有机构", "报告期", "备注"],
        _institutional_13f_current_concentration_rows(holdings, limit=limit),
        empty="暂无可用于计算当前13F集中度的机构持仓数据。",
    )


def _institutional_13f_increase_concentration_table(holdings: list[Mapping], limit: int = 5) -> str:
    return _table(
        ["标的", "发行人", "合计加仓/新建仓", "占加仓样本", "加仓机构数", "主要加仓/新建仓机构", "上期→最新合计市值", "比较区间", "备注"],
        _institutional_13f_delta_concentration_rows(holdings, direction="increase", limit=limit),
        empty="暂无足够的相邻两期 13F 数据或未检测到可比加仓/新建仓。请确保 INSTITUTIONAL_13F_FILINGS_PER_MANAGER=2 并成功采集最近两期13F。",
    )


def _institutional_13f_decrease_concentration_table(holdings: list[Mapping], limit: int = 5) -> str:
    return _table(
        ["标的", "发行人", "合计减仓/清仓", "占减仓样本", "减仓机构数", "主要减仓/清仓机构", "上期→最新合计市值", "比较区间", "备注"],
        _institutional_13f_delta_concentration_rows(holdings, direction="decrease", limit=limit),
        empty="暂无足够的相邻两期 13F 数据或未检测到可比减仓/清仓。请确保 INSTITUTIONAL_13F_FILINGS_PER_MANAGER=2 并成功采集最近两期13F。",
    )

def _new_items_summary_rows(
    business: list[Mapping],
    political: list[Mapping],
    oge_assets: list[Mapping],
    institutional_13f: list[Mapping],
    price_by_ticker: dict[str, float],
    new_since: str | None,
    limit: int = 18,
) -> list[list[str]]:
    # Daily-new overview is grouped by category + ticker/asset so the same
    # underlying target appears once, with whales/managers listed side by side.
    grouped: dict[tuple[str, str], dict] = {}

    def add_item(category: str, target: str, action: str, name: str, amount: float, date_text: str, desc: str, source_html: str) -> None:
        key = (category, target or "UNKNOWN")
        item = grouped.setdefault(key, {
            "class": "row-new",
            "sort": 0.0,
            "names": [],
            "actions": [],
            "dates": [],
            "descs": [],
            "sources": [],
            "amount": 0.0,
            "category": category,
            "target": target or "UNKNOWN",
        })
        if action and action not in item["actions"]:
            item["actions"].append(action)
        item["sort"] += max(float(amount or 0), 0.0)
        item["amount"] += max(float(amount or 0), 0.0)
        if name and name not in item["names"]:
            item["names"].append(name)
        if date_text and date_text not in item["dates"]:
            item["dates"].append(date_text)
        if desc and desc not in item["descs"]:
            item["descs"].append(desc)
        if source_html and source_html not in item["sources"]:
            item["sources"].append(source_html)

    for label, trades in [("商界交易", business), ("政界交易", political)]:
        new_trades = [x for x in trades if _is_new_trade(x, new_since) and not _is_oge_asset(x) and not _is_institutional_13f(x)]
        for t in _dedup_economic_trades(new_trades):
            obj = _raw_json_obj(t)
            amount = _trade_amount_for_display(t, price_by_ticker)[0]
            add_item(
                label,
                str(t.get("ticker") or ""),
                str(t.get("action") or ""),
                str(t.get("whale_name") or ""),
                amount,
                _display_trade_date(t),
                str(obj.get("asset_name") or obj.get("description") or t.get("company_name") or "")[:100],
                _source_link(t),
            )

    asset_new = [x for x in oge_assets if _is_new_trade(x, new_since) and _is_oge_asset(x)]
    for t in _dedup_economic_trades(asset_new):
        obj = _raw_json_obj(t)
        asset = str(obj.get("asset_name") or obj.get("description") or t.get("company_name") or t.get("ticker") or "")
        amount = _trade_amount_for_display(t, price_by_ticker)[0]
        add_item(
            "行政分支OGE资产/持仓",
            str(t.get("ticker") or asset[:40] or "非ticker资产"),
            str(t.get("action") or "HOLDING"),
            str(t.get("whale_name") or ""),
            amount,
            _display_report_date(t),
            asset[:100],
            _source_link(t),
        )

    for h in [x for x in institutional_13f if _is_new_trade(x, new_since)]:
        obj = _raw_json_obj(h)
        manager = str(obj.get("manager") or h.get("insider_role") or h.get("whale_name") or "")
        lead = str(obj.get("lead_investor") or "")
        name = f"{manager} / {lead}" if lead and lead not in manager else manager
        add_item(
            "机构13F持仓",
            str(h.get("ticker") or ""),
            "HOLDING_13F",
            name,
            _institutional_13f_amount_usd(h),
            str(obj.get("report_period") or h.get("trade_date") or "")[:10],
            str(obj.get("nameOfIssuer") or h.get("company_name") or "")[:100],
            _source_link(h),
        )

    items = sorted(grouped.values(), key=lambda x: x["sort"], reverse=True)
    rows = []
    for item in items[:limit]:
        cells = [
            escape(item["category"]),
            f"<b>{escape(item['target'])}</b>",
            escape(" / ".join(item["actions"][:4]) or "-"),
            escape("；".join(item["names"][:6]) or "-"),
            _money(item["amount"]),
            escape("；".join(item["dates"][:5]) or "-"),
            escape("；".join(item["descs"][:3]) or "-"),
            "；".join(item["sources"][:3]),
        ]
        rows.append(("row-new", cells))
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
    institutional_13f_holdings: list[Mapping] | None = None,
    new_since: str | None = None,
    baseline_trade_count: int = 0,
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    price_by_ticker = _market_price_map(market_context)
    buy_evidence = buy_evidence or []
    sell_evidence = sell_evidence or []
    core_buy_trades = core_buy_trades or []
    core_sell_trades = core_sell_trades or []
    oge_executive_trades = oge_executive_trades or []
    institutional_13f_holdings = institutional_13f_holdings or []

    all_recent = [t for t in recent_trades if _trade_date_ok(t) and not _is_institutional_13f(t)]
    # Political trading details must include only real BUY/SELL/EXCHANGE records.
    # OGE 278e / HOLDING assets are shown in the separate executive asset radar.
    political_trades = [t for t in all_recent if _is_political_or_oge(t) and not _is_oge_asset(t) and str(t.get("action") or "").upper() in {"BUY", "SELL", "EXCHANGE"}]
    political_trades += [t for t in oge_executive_trades if _trade_date_ok(t) and not _is_oge_asset(t) and str(t.get("action") or "").upper() in {"BUY", "SELL", "EXCHANGE"}]
    executive_asset_trades = [t for t in oge_executive_trades if _is_oge_asset(t) and _trade_date_ok(t)]
    # Trump is now handled as a normal political/executive whale, not a separate chapter.
    business_trades = [t for t in (core_buy_trades + core_sell_trades + buy_evidence + sell_evidence) if _trade_date_ok(t) and not _is_political_or_oge(t) and not _is_institutional_13f(t)]

    # If caller did not provide evidence tables, fall back to recent non-political records.
    if not business_trades:
        business_trades = [t for t in all_recent if not _is_political_or_oge(t) and not _is_institutional_13f(t) and str(t.get("action") or "").upper() in {"BUY", "SELL"}]

    if baseline_trade_count <= 0:
        change_class = "big-change"
        change_text = f"首次建立对比基线：本次入库 {new_trade_count} 条；明日开始仅显示真正新增/变化"
        change_note = "未检测到上一轮持久化数据库快照；本次用于建立基线，不应解读为今日全部新增。"
    elif new_trade_count > 0:
        change_class = "big-change"
        change_text = f"今日新增/变化披露记录：{new_trade_count} 条"
        change_note = f"已恢复上一轮数据库快照（基线 {baseline_trade_count} 条），本数字为本次新插入披露记录。"
    else:
        change_class = "no-change"
        change_text = "今日无新增重大变化"
        change_note = f"已恢复上一轮数据库快照（基线 {baseline_trade_count} 条），本次未发现新披露记录。"

    new_items_overview = _table(
        ["类别", "标的", "动作/口径", "巨鲸/机构", "金额/区间", "交易/报告日", "说明", "来源"],
        _new_items_summary_rows(business_trades, political_trades, executive_asset_trades, institutional_13f_holdings, price_by_ticker, new_since, limit=18),
        empty="今日未发现新的重点披露；可继续查看下方既有核心榜单。",
    )

    top_conclusions = _table(
        ["类别", "股票", "方向", "金额", "反向金额", "主要巨鲸", "交易日期", "变化"],
        _top_conclusion_rows(business_trades, political_trades, price_by_ticker, limit=10, new_since=new_since),
        empty="暂无达到阈值的巨鲸行动。",
    )
    business_chart = _ticker_comparison_chart(business_trades, price_by_ticker, top_tickers=10)
    political_chart = _ticker_comparison_chart(political_trades, price_by_ticker, top_tickers=12)
    business_summary = _action_summary_table(business_trades, price_by_ticker, limit=15)
    political_summary_table = _action_summary_table(political_trades, price_by_ticker, limit=18)
    business_details = _table(["交易日", "股票", "方向", "代码", "巨鲸", "角色", "金额", "标的说明", "来源"], _detail_rows(business_trades, price_by_ticker, limit=60, new_since=new_since))
    political_details = _table(["交易日", "股票/标的", "方向", "代码", "政界巨鲸", "角色", "金额", "标的说明", "来源"], _detail_rows(political_trades, price_by_ticker, limit=80, new_since=new_since))
    executive_assets = _table(["人物", "职位", "披露类型", "投资标的/描述", "动作", "金额/估值区间", "披露/报告日期", "来源"], _executive_asset_rows(executive_asset_trades, price_by_ticker, limit=40, new_since=new_since))
    institutional_13f_current_concentration_table = _institutional_13f_current_concentration_table(institutional_13f_holdings, limit=5)
    institutional_13f_increase_concentration_table = _institutional_13f_increase_concentration_table(institutional_13f_holdings, limit=5)
    institutional_13f_decrease_concentration_table = _institutional_13f_decrease_concentration_table(institutional_13f_holdings, limit=5)
    institutional_13f_table = _table(["机构", "代表人物", "标的", "发行人", "13F市值", "股数", "报告期", "披露日", "来源"], _institutional_13f_rows(institutional_13f_holdings, limit=50, new_since=new_since), empty="暂无机构巨鲸 13F 持仓披露。")

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
.change-new {{ background: #fed7aa; color: #9a3412; font-weight: 800; padding: 2px 6px; border-radius: 6px; }}
.change-existing {{ color: #6b7280; }}
tr.row-new td {{ background: #fff7ed; border-top: 2px solid #fdba74; border-bottom: 2px solid #fdba74; }}
</style>
</head>
<body>
<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>
<p class="small">生成时间：{escape(now)}；交易时间范围：{escape(settings.scan_start_date)} 至今；正式报告目标发送时间：柏林时间每日 08:00。</p>
<div class="{change_class}">{escape(change_text)}</div>
<p class="small">变化口径：{escape(change_note)}</p>
<p class="notice"><b>报告定位：</b>快速了解近期商界/政界巨鲸在美股及公开投资标的上的真金白银 BUY/SELL 披露。金额来自公开披露，政治期权默认按披露金额区间排序，名义敞口只作备注；本报告不构成个性化投资建议。</p>

<h2>一、今日结论总览</h2>
<p class="note">本部分集中展示所有核心图示。图示以股票/标的为纲，同一股票的 BUY 与 SELL 放在同一图组中对比，旁边列出主要巨鲸和交易日期。</p>
<h3>今日新增内容总览（相对上一轮成功运行）</h3>
{new_items_overview}
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

<h2>四、机构巨鲸 13F 持仓雷达</h2>
<p class="note">13F 是机构投资经理的季度持仓披露，不代表实时买入/卖出交易。表中的“报告期”是季度末持仓日，“披露日”是 13F 文件提交日。</p>
<h3>13F 最新持仓集中度 Top 5</h3>
<p class="small">口径：汇总 Top20 机构巨鲸最新一期 13F 已采集持仓，按同一股票在这些机构中的合计13F市值排序；13F 为季度末持仓，不代表实时交易。</p>
{institutional_13f_current_concentration_table}
<h3>13F 加仓 / 新建仓集中度 Top 5（最近两期）</h3>
<p class="small">口径：比较同一机构最近两期13F，汇总各机构对同一股票的正向变化；“新建仓”表示上一期未持有、本期持有。</p>
{institutional_13f_increase_concentration_table}
<h3>13F 减仓 / 清仓集中度 Top 5（最近两期）</h3>
<p class="small">口径：比较同一机构最近两期13F，汇总各机构对同一股票的负向变化绝对值；“清仓/退出”表示上一期持有、本期未持有。</p>
{institutional_13f_decrease_concentration_table}
<h3>机构巨鲸 13F 持仓明细</h3>
{institutional_13f_table}

<h2>五、口径说明</h2>
<ul>
<li>扫描交易日期从 {escape(settings.scan_start_date)} 起，2025 年及以前交易不进入正式正文。</li>
<li>政治期权交易同时保留“披露金额区间”和“期权名义敞口”说明；排名默认使用披露金额区间，避免把期权名义金额与现金成交金额混排。</li>
<li>已删除正文中的关联 SELL 审计、行情/基本面/新闻情绪、非主动/税务/授予审计和超长 BUY/SELL 明细；如后续需要，可单独生成附件。</li>
<li>13F 机构巨鲸模块反映季度末持仓和披露变化，不应解读为当日交易；新增/变化表示相对上一轮数据库新出现的 13F 披露记录。</li>
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
