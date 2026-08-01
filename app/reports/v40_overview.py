from __future__ import annotations

import json
from html import escape
from typing import Iterable, Mapping

from app.domain.trade_classification import is_asset_or_holding_disclosure, is_primary_transaction


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
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
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
    if not url:
        return escape(label)
    return f'<a href="{escape(url)}">{escape(label)}</a>'


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


def _category(row: Mapping[str, object]) -> str:
    source = str(row.get("source") or "").upper()
    action = str(row.get("action") or "").upper()
    if source == "INSTITUTIONAL_13F" or action == "HOLDING_13F":
        return "机构13F持仓"
    if is_asset_or_holding_disclosure(row):
        return "行政分支资产披露"
    if is_primary_transaction(row):
        return "主动交易"
    return "其他披露"


def build_daily_changes_overview(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None,
    limit: int = 30,
) -> str:
    """Render only newly inserted or materially changed rows for the current run."""

    new_rows = [dict(row) for row in rows if _is_new(row, new_since)]
    new_rows.sort(
        key=lambda row: (
            str(row.get("created_at") or ""),
            _float(row.get("amount_usd")),
        ),
        reverse=True,
    )

    body: list[str] = []
    for row in new_rows[:limit]:
        raw = _raw(row)
        actor = str(row.get("whale_name") or raw.get("manager") or "-")
        action = str(row.get("action") or "-").upper()
        date_value = str(
            row.get("trade_date")
            or raw.get("report_period")
            or row.get("filing_date")
            or "-"
        )[:10]
        amount_label = str(raw.get("amount_range_label") or "").strip()
        amount = amount_label or _money(row.get("amount_usd"))
        ticker = str(row.get("ticker") or "").strip().upper()
        target = _asset_name(row)
        if ticker and ticker not in target.upper():
            target = f"{ticker} — {target}"

        body.append(
            '<tr class="row-new">'
            f"<td>{escape(_category(row))}</td>"
            f"<td>{escape(target[:180])}</td>"
            f"<td>{escape(action)}</td>"
            f"<td>{escape(actor[:120])}</td>"
            f"<td>{escape(amount)}</td>"
            f"<td>{escape(date_value or '-')}</td>"
            f"<td>{_source(row)}</td>"
            "</tr>"
        )

    if body:
        content = (
            "<table><thead><tr>"
            "<th>类别</th><th>标的/资产</th><th>动作/口径</th><th>人物/机构</th>"
            "<th>金额/区间</th><th>交易/报告日</th><th>来源</th>"
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        )
        note = f"本次共识别 {len(new_rows)} 条新增或变化记录；以下显示前 {min(limit, len(new_rows))} 条。"
    else:
        content = "<p>本次运行未识别到新增或实质变化记录。</p>"
        note = "仅展示相对上一轮持久化数据库新插入的记录。"

    return (
        '<section id="v40-daily-changes-overview">'
        '<h2>今日新增内容总览</h2>'
        f'<p class="small">{escape(note)} 新增或变化内容统一整行橙色高亮。</p>'
        + content
        + "</section>"
    )
