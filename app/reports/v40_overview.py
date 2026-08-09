from __future__ import annotations

from collections import Counter, defaultdict
from html import escape
import json
import re
from typing import Iterable, Mapping

from app.domain.asset_semantics import parse_oge_asset_semantics
from app.domain.trade_classification import (
    is_asset_or_holding_disclosure,
    is_credible_directional_transaction,
)


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _money(value: object) -> str:
    amount = _float(value)
    if amount >= 1_000_000_000:
        return f"${amount / 1_000_000_000:.2f}B"
    if amount >= 1_000_000:
        return f"${amount / 1_000_000:.2f}M"
    if amount >= 1_000:
        return f"${amount / 1_000:.1f}K"
    return f"${amount:.0f}" if amount else "-"


def _raw(row: Mapping[str, object]) -> dict:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _is_new(row: Mapping[str, object], new_since: str | None) -> bool:
    if not new_since:
        return False
    created_at = str(row.get("created_at") or "")[:19]
    return bool(created_at and created_at >= str(new_since)[:19])


def _source(row: Mapping[str, object]) -> str:
    label = str(row.get("source") or "-")
    url = str(row.get("filing_url") or "")
    return f'<a href="{escape(url)}">{escape(label)}</a>' if url else escape(label)


def _asset_name(row: Mapping[str, object]) -> str:
    raw = _raw(row)
    return str(
        raw.get("asset_name")
        or raw.get("description")
        or raw.get("nameOfIssuer")
        or row.get("company_name")
        or row.get("ticker")
        or "-"
    )


_OGE_HEADER_RE = re.compile(
    r"^(?:\s*#?\s*)?(?:employer or party\b|city,?\s*state\s+status and terms\b|assets? and income\b|description\b)",
    re.I,
)


def _is_trusted_oge_asset(row: Mapping[str, object]) -> bool:
    text = re.sub(r"\s+", " ", _asset_name(row)).strip()
    if not text or _OGE_HEADER_RE.search(text):
        return False
    parsed = parse_oge_asset_semantics(text)
    return parsed.quality == "accepted" and bool(parsed.asset_name and parsed.canonical_key)


def _bucket(row: Mapping[str, object]) -> str:
    source = str(row.get("source") or "").upper()
    action = str(row.get("action") or "").upper()
    if source == "INSTITUTIONAL_13F" or action == "HOLDING_13F":
        return "13F"
    if is_asset_or_holding_disclosure(row):
        if (source == "OGE_EXECUTIVE_ASSET" or action in {"HOLDING", "DISCLOSURE"}) and _is_trusted_oge_asset(row):
            return "OGE"
        return "其他披露"
    if is_credible_directional_transaction(row):
        if source.startswith("POLITICAL"):
            return "政治交易"
        if action == "BUY":
            return "主动买入"
        if action == "SELL":
            return "主动卖出"
        return "其他主动交易"
    return "其他披露"


def _display_category(bucket: str) -> str:
    return {
        "主动买入": "主动买入",
        "主动卖出": "主动卖出",
        "政治交易": "政治交易",
        "OGE": "行政分支资产披露",
        "13F": "机构13F持仓",
        "其他主动交易": "其他主动交易",
        "其他披露": "其他披露",
    }.get(bucket, bucket)


def _row_html(row: Mapping[str, object], bucket: str) -> str:
    raw = _raw(row)
    actor = str(row.get("whale_name") or raw.get("manager") or "-")
    action = str(row.get("action") or "-").upper()
    date_value = str(row.get("trade_date") or raw.get("report_period") or row.get("filing_date") or "-")[:10]
    amount_label = str(raw.get("amount_range_label") or "").strip()
    amount = amount_label or _money(row.get("amount_usd"))
    ticker = str(row.get("ticker") or "").strip().upper()
    target = _asset_name(row)
    if bucket == "OGE":
        parsed = parse_oge_asset_semantics(target)
        if parsed.quality == "accepted" and parsed.asset_name:
            target = parsed.asset_name
    if ticker and ticker not in target.upper() and bucket != "OGE":
        target = f"{ticker} — {target}"
    return (
        '<tr class="row-new">'
        f"<td>{escape(_display_category(bucket))}</td><td>{escape(target[:180])}</td>"
        f"<td>{escape(action)}</td><td>{escape(actor[:120])}</td>"
        f"<td>{escape(amount)}</td><td>{escape(date_value or '-')}</td><td>{_source(row)}</td></tr>"
    )


def build_daily_changes_overview(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None,
    limit: int = 30,
) -> str:
    """Balanced overview using the same trustworthy-record quality basis as the header."""
    new_rows = [dict(row) for row in rows if _is_new(row, new_since)]
    groups: dict[str, list[dict]] = defaultdict(list)
    for row in new_rows:
        bucket = _bucket(row)
        if bucket == "其他披露":
            continue
        groups[bucket].append(row)
    for group in groups.values():
        group.sort(key=lambda row: _float(row.get("amount_usd")), reverse=True)

    counts = Counter({bucket: len(group) for bucket, group in groups.items()})
    order = ["主动买入", "主动卖出", "政治交易", "OGE", "13F", "其他主动交易"]
    summary = "；".join(f"{_display_category(bucket)} {counts.get(bucket, 0)}" for bucket in order)

    selected: list[tuple[str, dict]] = []
    per_bucket = max(3, min(5, limit // max(1, len([b for b in order if groups.get(b)]))))
    for bucket in order:
        selected.extend((bucket, row) for row in groups.get(bucket, [])[:per_bucket])
    selected_keys = {id(row) for _, row in selected}
    remainder = [
        (bucket, row)
        for bucket in order
        for row in groups.get(bucket, [])
        if id(row) not in selected_keys
    ]
    remainder.sort(key=lambda item: _float(item[1].get("amount_usd")), reverse=True)
    selected.extend(remainder[: max(0, limit - len(selected))])
    selected = selected[:limit]

    body = [_row_html(row, bucket) for bucket, row in selected]
    if body:
        content = (
            "<table><thead><tr><th>类别</th><th>标的/资产</th><th>动作/口径</th><th>人物/机构</th>"
            "<th>金额/区间</th><th>交易/报告日</th><th>来源</th></tr></thead><tbody>"
            + "".join(body) + "</tbody></table>"
        )
        note = f"本次新增可信记录 {sum(counts.values())} 条：{summary}。各类别优先展示，再按金额补足前 {len(selected)} 条。"
    else:
        content = "<p>本次运行未识别到新增或实质变化记录。</p>"
        note = "仅展示相对上一轮持久化数据库新插入、且通过质量校验的记录。"

    return (
        '<section id="v40-daily-changes-overview"><h2>今日新增内容总览</h2>'
        f'<p class="small">{escape(note)} 新增或变化内容统一整行橙色高亮。</p>'
        + content + "</section>"
    )


is_trusted_oge_asset_for_tests = _is_trusted_oge_asset
