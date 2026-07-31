from __future__ import annotations

from html import escape
import json
import re
from typing import Iterable, Mapping


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


def _asset_text(row: Mapping[str, object]) -> tuple[str, str]:
    raw = _raw(row)
    asset = str(
        raw.get("asset_name")
        or raw.get("name")
        or raw.get("description")
        or row.get("company_name")
        or row.get("ticker")
        or "未命名资产"
    ).strip()
    description = str(raw.get("description") or raw.get("context") or "").strip()
    return asset, description


def classify_oge_asset(row: Mapping[str, object]) -> str:
    asset, description = _asset_text(row)
    text = f"{asset} {description}".lower()
    rules = [
        ("加密资产", r"bitcoin|ethereum|crypto|digital asset|token|区块链|加密"),
        ("房地产/商业权益", r"real estate|property|land|building|commercial|business interest|房地产|不动产"),
        ("私募/LLC/信托", r"\bllc\b|limited partnership|private equity|venture|trust|lp\b|私募|信托"),
        ("债券", r"bond|treasury|note|municipal|fixed income|debt|债券|国债"),
        ("ETF/基金", r"\betf\b|fund|mutual|index fund|基金"),
        ("股票", r"common stock|ordinary shares|equity|stock|shares|股票|股份"),
    ]
    for label, pattern in rules:
        if re.search(pattern, text, re.I):
            return label
    ticker = str(row.get("ticker") or "").strip()
    if ticker and not ticker.upper().startswith("OGE"):
        return "股票/上市证券"
    return "其他资产"


def _dedup_key(row: Mapping[str, object]) -> tuple[str, ...]:
    raw = _raw(row)
    asset, description = _asset_text(row)
    return (
        str(row.get("whale_name") or "").strip().lower(),
        asset.lower(),
        description.lower(),
        str(row.get("filing_date") or row.get("trade_date") or "")[:10],
        str(raw.get("amount_range_label") or "").strip(),
        str(row.get("filing_url") or row.get("source_id") or ""),
    )


def build_cabinet_oge_radar(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
    limit: int = 50,
) -> str:
    """Render executive-branch OGE holdings across all disclosed asset classes."""

    deduped: dict[tuple[str, ...], dict] = {}
    for source_row in rows:
        if not _is_oge_asset(source_row):
            continue
        key = _dedup_key(source_row)
        if key not in deduped:
            deduped[key] = dict(source_row)
        elif _is_new(source_row, new_since):
            deduped[key]["created_at"] = source_row.get("created_at")

    ordered = sorted(
        deduped.values(),
        key=lambda row: (
            _is_new(row, new_since),
            str(row.get("filing_date") or row.get("trade_date") or "")[:10],
            _float(row.get("amount_usd")),
        ),
        reverse=True,
    )[:limit]

    body: list[str] = []
    for row in ordered:
        raw = _raw(row)
        asset, description = _asset_text(row)
        category = classify_oge_asset(row)
        amount_label = str(raw.get("amount_range_label") or raw.get("value_range") or "").strip()
        midpoint = _money(_float(row.get("amount_usd")))
        amount = amount_label + (f"（中点 {midpoint}）" if amount_label and midpoint != "-" else "")
        if not amount:
            amount = midpoint
        report_date = str(raw.get("report_period") or row.get("filing_date") or row.get("trade_date") or "")[:10] or "-"
        url = str(row.get("filing_url") or "")
        source = escape(str(row.get("source") or "OGE"))
        source_html = f'<a href="{escape(url)}">{source}</a>' if url else source
        row_class = ' class="row-new"' if _is_new(row, new_since) else ""
        body.append(
            f"<tr{row_class}>"
            f"<td>{escape(str(row.get('whale_name') or '-'))}</td>"
            f"<td>{escape(str(row.get('insider_role') or '-'))}</td>"
            f"<td>{escape(category)}</td>"
            f"<td><b>{escape(asset)}</b>"
            + (f"<br><span class=\"small\">{escape(description[:180])}</span>" if description and description != asset else "")
            + "</td>"
            f"<td>{escape(amount or '-')}</td>"
            f"<td>{escape(report_date)}</td>"
            f"<td>{source_html}</td>"
            "</tr>"
        )

    table = (
        "<p>暂无可展示的行政分支 OGE 资产披露。</p>"
        if not body
        else "<table><thead><tr>"
        "<th>人物</th><th>职位</th><th>资产类别</th><th>投资标的及简要描述</th>"
        "<th>金额/区间</th><th>披露/报告日期</th><th>来源</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )
    return (
        '<section id="v40-cabinet-oge-radar">'
        '<h2>部长 / Cabinet OGE 披露雷达</h2>'
        '<p class="small">覆盖股票、ETF/基金、债券、私募/LLC/信托、房地产/商业权益、加密资产及其他公开披露资产。'
        '非上市资产保留原始名称，不强制映射为美股代码；本板块不计入主交易排名。</p>'
        + table
        + "</section>"
    )
