from __future__ import annotations

from datetime import date, datetime
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


def _clean_text(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -|;,")
    text = re.sub(r"^(?:N/A|No)\s+", "", text, flags=re.I)
    return text


def _asset_text(row: Mapping[str, object]) -> tuple[str, str]:
    raw = _raw(row)
    asset = _clean_text(
        raw.get("asset_name")
        or raw.get("name")
        or raw.get("description")
        or row.get("company_name")
        or row.get("ticker")
        or ""
    )
    description = _clean_text(raw.get("description") or raw.get("context") or "")
    return asset or "未命名资产", description


def _is_fragment(asset: str) -> bool:
    text = asset.strip()
    lowered = text.lower()
    if len(text) < 5:
        return True
    fragment_exact = {
        "n/a", "interest", "dividends", "capital gains dividends", "borrower)",
        "rate term", "see endnote", "none (or less", "no net distributive",
    }
    if lowered in fragment_exact:
        return True
    if re.fullmatch(r"(?:n/a\s*)?(?:over|\$)[\d,]+(?:\.\d+)?", lowered):
        return True
    if any(token in lowered for token in ("# employer or party city", "status and terms date")):
        return True
    return False


def classify_oge_asset(row: Mapping[str, object]) -> str:
    asset, description = _asset_text(row)
    text = f"{asset} {description}".lower()
    rules = [
        ("加密资产", r"bitcoin|ethereum|crypto|digital asset|token|区块链|加密"),
        ("房地产/商业权益", r"real estate|property|land held|commercial real estate|mixed use|business interest|房地产|不动产"),
        ("私募/LLC/信托", r"\bllc\b|limited partnership|private equity|venture|trust|\bl\.p\.\b|私募|信托"),
        ("ETF/基金", r"\betf\b|mutual fund|index fund|investment fund|基金"),
        ("债券", r"\bbond\b|treasury (?:bond|note|bill)|municipal bond|fixed income|debenture|债券|国债"),
        ("股票/上市证券", r"common stock|ordinary shares|class [ab] shares?|\([A-Z]{1,5}\)|publicly traded|股票|股份"),
    ]
    for label, pattern in rules:
        if re.search(pattern, text, re.I):
            return label
    ticker = str(row.get("ticker") or "").strip()
    if ticker and not ticker.upper().startswith("OGE"):
        return "股票/上市证券"
    return "其他资产"


def _valid_report_date(row: Mapping[str, object]) -> str:
    raw = _raw(row)
    candidates = [row.get("filing_date"), row.get("trade_date"), raw.get("report_period")]
    today = date.today()
    for candidate in candidates:
        value = str(candidate or "")[:10]
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            continue
        if parsed <= today:
            return value
    return "日期待核验"


def _dedup_key(row: Mapping[str, object]) -> tuple[str, ...]:
    raw = _raw(row)
    asset, _ = _asset_text(row)
    normalized = re.sub(r"\b(?:n/a|see endnote|no)\b", "", asset, flags=re.I)
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return (
        str(row.get("whale_name") or "").strip().lower(),
        normalized,
        str(raw.get("amount_range_label") or "").strip(),
        str(row.get("filing_url") or row.get("source_id") or ""),
    )


def build_cabinet_oge_radar(
    rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
    limit: int = 18,
) -> str:
    """Render a concise, quality-filtered executive-branch OGE asset radar."""

    deduped: dict[tuple[str, ...], dict] = {}
    for source_row in rows:
        if not _is_oge_asset(source_row):
            continue
        asset, _ = _asset_text(source_row)
        if _is_fragment(asset):
            continue
        key = _dedup_key(source_row)
        current = deduped.get(key)
        if current is None or _float(source_row.get("amount_usd")) > _float(current.get("amount_usd")):
            deduped[key] = dict(source_row)
        elif _is_new(source_row, new_since):
            current["created_at"] = source_row.get("created_at")

    ordered = sorted(
        deduped.values(),
        key=lambda row: (_is_new(row, new_since), _float(row.get("amount_usd"))),
        reverse=True,
    )[:limit]

    body: list[str] = []
    for row in ordered:
        raw = _raw(row)
        asset, description = _asset_text(row)
        category = classify_oge_asset(row)
        amount_label = _clean_text(raw.get("amount_range_label") or raw.get("value_range") or "")
        midpoint = _money(_float(row.get("amount_usd")))
        amount = amount_label + (f"（估算中点 {midpoint}）" if amount_label and midpoint != "-" else "")
        if not amount:
            amount = midpoint
        url = str(row.get("filing_url") or "")
        source = escape(str(row.get("source") or "OGE"))
        source_html = f'<a href="{escape(url)}">{source}</a>' if url else source
        row_class = ' class="row-new"' if _is_new(row, new_since) else ""
        body.append(
            f"<tr{row_class}>"
            f"<td>{escape(str(row.get('whale_name') or '-'))}</td>"
            f"<td>{escape(str(row.get('insider_role') or '-'))}</td>"
            f"<td>{escape(category)}</td>"
            f"<td><b>{escape(asset[:180])}</b>"
            + (f"<br><span class=\"small\">{escape(description[:140])}</span>" if description and description != asset else "")
            + "</td>"
            f"<td>{escape(amount or '-')}</td>"
            f"<td>{escape(_valid_report_date(row))}</td>"
            f"<td>{source_html}</td>"
            "</tr>"
        )

    table = (
        "<p>暂无通过数据质量检查的行政分支 OGE 资产披露。</p>"
        if not body
        else "<table><thead><tr>"
        "<th>人物</th><th>职位</th><th>资产类别</th><th>投资标的及简要描述</th>"
        "<th>金额/区间</th><th>披露/报告日期</th><th>来源</th>"
        "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
    )
    return (
        '<section id="v40-cabinet-oge-radar">'
        '<h2>部长 / Cabinet OGE 披露雷达</h2>'
        '<p class="small">仅展示通过碎片过滤和去重的高价值记录，邮件正文最多18行。'
        '金额为公开区间或估算中点；未来或异常日期显示“日期待核验”。本板块不计入主交易排名。</p>'
        + table
        + "</section>"
    )
