from __future__ import annotations

from collections import defaultdict
from html import escape
import re
from typing import Iterable, Mapping

from app.db import fetch_institutional_13f_holdings, fetch_oge_executive_trades
from app.domain.trade_classification import is_primary_transaction
from app.reports.v40_oge import build_cabinet_oge_radar, passes_v42_report_gate_for_tests
from app.reports.v40_overview import build_daily_changes_overview


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _economic_key(row: Mapping[str, object]) -> tuple[str, ...]:
    return (
        str(row.get("ticker") or "").strip().upper(),
        str(row.get("action") or "").strip().upper(),
        str(row.get("transaction_code") or "").strip().upper(),
        str(row.get("trade_date") or "")[:10],
        str(row.get("filing_date") or "")[:10],
        str(row.get("accession_number") or row.get("filing_url") or row.get("source_id") or ""),
        f"{_float(row.get('amount_usd')):.4f}",
        f"{_float(row.get('shares')):.4f}",
        f"{_float(row.get('price')):.4f}",
        str(row.get("source") or "").strip().upper(),
    )


def _is_new(row: Mapping[str, object], new_since: str | None) -> bool:
    if not new_since:
        return False
    created_at = str(row.get("created_at") or "")[:19]
    return bool(created_at and created_at >= str(new_since)[:19])


def _is_dubious_political_amount(row: Mapping[str, object]) -> bool:
    source = str(row.get("source") or "").upper()
    amount = _float(row.get("amount_usd"))
    return source.startswith("POLITICAL") and 0 < amount < 100


def build_active_buy_radar(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
    limit: int = 20,
) -> str:
    deduped: dict[tuple[str, ...], dict] = {}
    for source_row in rows:
        if not is_primary_transaction(source_row):
            continue
        if str(source_row.get("action") or "").upper() != "BUY":
            continue
        if _is_dubious_political_amount(source_row):
            continue
        ticker = str(source_row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        key = _economic_key(source_row)
        reporter = str(source_row.get("whale_name") or "").strip()
        if key not in deduped:
            row = dict(source_row)
            row["_reporters"] = [reporter] if reporter else []
            row["_is_new"] = _is_new(source_row, new_since)
            deduped[key] = row
        else:
            if reporter and reporter not in deduped[key]["_reporters"]:
                deduped[key]["_reporters"].append(reporter)
            deduped[key]["_is_new"] = bool(deduped[key]["_is_new"] or _is_new(source_row, new_since))

    grouped: dict[str, dict] = defaultdict(lambda: {
        "amount": 0.0,
        "trades": 0,
        "reporters": set(),
        "dates": set(),
        "sources": set(),
        "is_new": False,
    })
    for row in deduped.values():
        ticker = str(row.get("ticker") or "").strip().upper()
        item = grouped[ticker]
        item["amount"] += max(0.0, _float(row.get("amount_usd")))
        item["trades"] += 1
        item["reporters"].update(row.get("_reporters") or [])
        date_value = str(row.get("trade_date") or row.get("filing_date") or "")[:10]
        if date_value:
            item["dates"].add(date_value)
        source = str(row.get("source") or "").strip()
        if source:
            item["sources"].add(source)
        item["is_new"] = bool(item["is_new"] or row.get("_is_new"))

    ordered = sorted(grouped.items(), key=lambda pair: pair[1]["amount"], reverse=True)[:limit]
    body: list[str] = []
    for rank, (ticker, item) in enumerate(ordered, start=1):
        reporters = sorted(item["reporters"])
        reporter_text = ", ".join(reporters[:4])
        if len(reporters) > 4:
            reporter_text += f" 等{len(reporters)}人/机构"
        dates = ", ".join(sorted(item["dates"], reverse=True)[:3]) or "-"
        sources = ", ".join(sorted(item["sources"])) or "-"
        row_class = ' class="row-new"' if item["is_new"] else ""
        body.append(
            f"<tr{row_class}><td>{rank}</td><td><b>{escape(ticker)}</b></td>"
            f"<td><b>P/BUY</b></td><td>{escape(_money(item['amount']))}</td>"
            f"<td>{item['trades']}</td><td>{escape(reporter_text or '-')}</td>"
            f"<td>{escape(dates)}</td><td>{escape(sources)}</td></tr>"
        )

    table_html = "<p>暂无金额口径可信的主动买入交易。</p>" if not body else (
        "<table><thead><tr><th>#</th><th>股票</th><th>信号</th><th>去重买入金额</th>"
        "<th>独立交易数</th><th>真实交易人/机构</th><th>交易日期</th><th>来源</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )
    return (
        '<section id="v40-active-buy-radar"><h2>主动买入雷达（P/BUY，按去重买入金额）</h2>'
        '<p class="small">仅统计真实 BUY 交易；联合申报人合并展示，金额只计算一次。'
        '政治披露中低于100美元的异常解析值暂不进入排名；OGE与13F持仓不进入本榜单。</p>'
        + table_html + "</section>"
    )


def _remove_named_table_column(html: str, header_name: str) -> str:
    table_pattern = re.compile(r"<table\b[^>]*>.*?</table>", re.I | re.S)
    cell_pattern = re.compile(r"<(th|td)\b[^>]*>.*?</\1>", re.I | re.S)

    def clean_table(match: re.Match[str]) -> str:
        table = match.group(0)
        header_match = re.search(r"<thead\b[^>]*>.*?<tr\b[^>]*>(.*?)</tr>.*?</thead>", table, re.I | re.S)
        if not header_match:
            return table
        headers = list(cell_pattern.finditer(header_match.group(1)))
        index = None
        for idx, header in enumerate(headers):
            text = re.sub(r"<[^>]+>", "", header.group(0)).strip()
            if text == header_name:
                index = idx
                break
        if index is None:
            return table

        def clean_row(row_match: re.Match[str]) -> str:
            row = row_match.group(0)
            cells = list(cell_pattern.finditer(row))
            if index >= len(cells):
                return row
            target = cells[index]
            return row[: target.start()] + row[target.end() :]

        return re.sub(r"<tr\b[^>]*>.*?</tr>", clean_row, table, flags=re.I | re.S)

    return table_pattern.sub(clean_table, html)


def _remove_legacy_new_overview(html: str) -> str:
    pattern = re.compile(
        r"<h3>今日新增内容总览（相对上一轮成功运行）</h3>.*?(?=<h3>|<h2>|</body>)",
        re.I | re.S,
    )
    return pattern.sub("", html)


def _clear_legacy_new_highlights(html: str) -> str:
    return re.sub(r'<tr\s+class="row-new">', "<tr>", html, flags=re.I)


def _row_dicts(rows: Iterable[object]) -> list[dict]:
    result: list[dict] = []
    for row in rows:
        result.append({key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row))
    return result


def _oge_rows() -> list[dict]:
    try:
        return _row_dicts(fetch_oge_executive_trades(limit=800))
    except Exception:
        return []


def _institutional_rows() -> list[dict]:
    try:
        return _row_dicts(fetch_institutional_13f_holdings("1900-01-01", limit=5000))
    except Exception:
        return []


def _asset_text(row: Mapping[str, object]) -> str:
    import json
    value = row.get("raw_json")
    raw = value if isinstance(value, dict) else {}
    if not raw:
        try:
            parsed = json.loads(str(value or ""))
            raw = parsed if isinstance(parsed, dict) else {}
        except Exception:
            raw = {}
    return str(raw.get("asset_name") or raw.get("name") or raw.get("description") or row.get("company_name") or row.get("ticker") or "")


def _trusted_new_count(primary_rows: list[dict], oge_rows: list[dict], institutional_rows: list[dict], new_since: str | None) -> int:
    primary_count = sum(1 for row in primary_rows if _is_new(row, new_since) and is_primary_transaction(row))
    oge_count = sum(
        1 for row in oge_rows
        if _is_new(row, new_since) and passes_v42_report_gate_for_tests(_asset_text(row))
    )
    institutional_count = sum(
        1 for row in institutional_rows
        if _is_new(row, new_since)
        and (str(row.get("source") or "").upper() == "INSTITUTIONAL_13F" or str(row.get("action") or "").upper() == "HOLDING_13F")
    )
    return primary_count + oge_count + institutional_count


def _replace_header_change_count(html: str, count: int) -> str:
    replacement = (
        f'<div class="big-change">今日新增/变化可信记录：{count} 条</div>'
        if count > 0 else '<div class="no-change">今日无新增重大变化</div>'
    )
    updated = re.sub(r'<div class="(?:big-change|no-change)">.*?</div>', replacement, html, count=1, flags=re.I | re.S)
    note = f'<p class="small">变化口径：与“今日新增内容总览”完全一致，仅统计本次新插入且通过质量校验的可信记录。</p>'
    updated = re.sub(r'<p class="small">变化口径：.*?</p>', note, updated, count=1, flags=re.I | re.S)
    return updated


def apply_v40_report_layout(
    html: str,
    primary_rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
) -> str:
    primary_rows = [dict(row) for row in primary_rows]
    oge_rows = _oge_rows()
    institutional_rows = _institutional_rows()

    updated = _remove_named_table_column(html, "净额")
    updated = _remove_legacy_new_overview(updated)
    updated = _clear_legacy_new_highlights(updated)
    updated = _replace_header_change_count(
        updated,
        _trusted_new_count(primary_rows, oge_rows, institutional_rows, new_since),
    )

    overview = build_daily_changes_overview(
        [*primary_rows, *oge_rows, *institutional_rows],
        new_since=new_since,
    )
    active_radar = build_active_buy_radar(primary_rows, new_since=new_since)
    oge_radar = build_cabinet_oge_radar(oge_rows, new_since=new_since)
    overlay = overview + active_radar + oge_radar

    first_h2 = re.search(r"<h2\b", updated, re.I)
    if first_h2:
        return updated[: first_h2.start()] + overlay + updated[first_h2.start() :]
    body_end = re.search(r"</body>", updated, re.I)
    if body_end:
        return updated[: body_end.start()] + overlay + updated[body_end.start() :]
    return updated + overlay


trusted_new_count_for_tests = _trusted_new_count
replace_header_change_count_for_tests = _replace_header_change_count
