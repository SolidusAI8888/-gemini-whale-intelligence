from __future__ import annotations

from datetime import date
from html import escape
import json
from typing import Iterable, Mapping

from app.domain.asset_semantics import parse_oge_asset_semantics


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
    return f"${value:.0f}" if value > 0 else "-"


def _raw(row: Mapping[str, object]) -> dict:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _is_oge_asset(row: Mapping[str, object]) -> bool:
    source = str(row.get("source") or "").upper()
    action = str(row.get("action") or "").upper()
    return source == "OGE_EXECUTIVE_ASSET" or action in {"HOLDING", "DISCLOSURE"}


def _is_new(row: Mapping[str, object], new_since: str | None) -> bool:
    if not new_since:
        return False
    created_at = str(row.get("created_at") or "")[:19]
    return bool(created_at and created_at >= str(new_since)[:19])


def _raw_asset_text(row: Mapping[str, object]) -> str:
    raw = _raw(row)
    return str(
        raw.get("asset_name")
        or raw.get("name")
        or raw.get("description")
        or row.get("company_name")
        or row.get("ticker")
        or ""
    )


def classify_oge_asset(row: Mapping[str, object]) -> str:
    return parse_oge_asset_semantics(_raw_asset_text(row)).category


def _report_date(row: Mapping[str, object]) -> str:
    raw = _raw(row)
    value = str(raw.get("report_period") or row.get("filing_date") or row.get("trade_date") or "")[:10]
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return "日期待核验"
    if parsed > date.today():
        return "日期待核验"
    return value


def build_cabinet_oge_radar(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
    limit: int = 18,
) -> str:
    deduped: dict[tuple[str, str, str], dict] = {}
    for source_row in rows:
        if not _is_oge_asset(source_row):
            continue
        parsed = parse_oge_asset_semantics(_raw_asset_text(source_row))
        if parsed.quality != "accepted" or not parsed.canonical_key or not parsed.asset_name:
            continue
        key = (
            str(source_row.get("whale_name") or "").strip().lower(),
            str(source_row.get("filing_url") or source_row.get("source_id") or ""),
            parsed.canonical_key,
        )
        candidate = dict(source_row)
        candidate["_normalized_asset_name"] = parsed.asset_name
        candidate["_normalized_asset_category"] = parsed.category
        current = deduped.get(key)
        if current is None or _float(candidate.get("amount_usd")) > _float(current.get("amount_usd")):
            deduped[key] = candidate
        elif _is_new(candidate, new_since):
            current["created_at"] = candidate.get("created_at")

    ordered = sorted(
        deduped.values(),
        key=lambda row: (_is_new(row, new_since), _float(row.get("amount_usd"))),
        reverse=True,
    )[:limit]

    body: list[str] = []
    for row in ordered:
        raw = _raw(row)
        asset = str(row.get("_normalized_asset_name") or "-")
        category = str(row.get("_normalized_asset_category") or "其他资产")
        amount_label = str(raw.get("amount_range_label") or raw.get("value_range") or "").strip()
        midpoint = _money(_float(row.get("amount_usd")))
        amount = amount_label + (f"（估算中点 {midpoint}）" if amount_label and midpoint != "-" else "")
        if not amount:
            amount = midpoint
        url = str(row.get("filing_url") or "")
        source = escape(str(row.get("source") or "OGE"))
        source_html = f'<a href="{escape(url)}">{source}</a>' if url else source
        row_class = ' class="row-new"' if _is_new(row, new_since) else ""
        body.append(
            f"<tr{row_class}><td>{escape(str(row.get('whale_name') or '-'))}</td>"
            f"<td>{escape(str(row.get('insider_role') or '-'))}</td>"
            f"<td>{escape(category)}</td><td><b>{escape(asset)}</b></td>"
            f"<td>{escape(amount or '-')}</td><td>{escape(_report_date(row))}</td><td>{source_html}</td></tr>"
        )

    table = "<p>暂无通过质量校验的行政分支 OGE 资产披露。</p>" if not body else (
        "<table><thead><tr><th>人物</th><th>职位</th><th>资产类别</th><th>标准化投资标的</th>"
        "<th>金额/区间</th><th>披露/报告日期</th><th>来源</th></tr></thead><tbody>"
        + "".join(body) + "</tbody></table>"
    )
    return (
        '<section id="v40-cabinet-oge-radar"><h2>部长 / Cabinet OGE 披露雷达</h2>'
        '<p class="small">V41 语义解析层先拆分资产、金额、收益类型与融资条款，再对标准化资产实体分类和去重。'
        '金额、收益类型、融资条款、表头和脚注不会作为资产展示；同一人物同一申报文件中的同一标准化资产只保留一条，邮件正文最多18行。</p>'
        + table + "</section>"
    )
