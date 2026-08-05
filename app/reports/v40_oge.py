from __future__ import annotations

from datetime import date
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
    text = re.sub(r"\s+", " ", str(value or "")).strip(" -:;,")
    text = re.sub(r"^(?:\d+(?:\.\d+)*\s+)+", "", text)
    text = re.sub(r"\s+(?:N/A\s+)?(?:Over|\$)[\s\$\d,–-]+$", "", text, flags=re.I)
    text = re.sub(r"\s+See Endnote\b.*$", "", text, flags=re.I)
    return text.strip(" -:;,")


def _asset_text(row: Mapping[str, object]) -> tuple[str, str]:
    raw = _raw(row)
    asset = _clean_text(
        raw.get("asset_name")
        or raw.get("name")
        or raw.get("description")
        or row.get("company_name")
        or row.get("ticker")
    )
    description = _clean_text(raw.get("context") or "")
    return asset or "未命名资产", description


_FRAGMENT_PATTERNS = (
    r"^(?:n/?a|none|no|yes|rate term|borrower\)?|see endnote|over \$?[\d,]+)$",
    r"^(?:interest|dividends?|capital gains?|rent or royalties|net distributive|crop sales)$",
    r"^(?:government guaranteed collateral|secured facility|on demand)$",
    r"# employer or party|status and terms|date$",
)


def _is_fragment(asset: str) -> bool:
    text = asset.strip().lower()
    if len(text) < 5:
        return True
    if any(re.search(pattern, text, re.I) for pattern in _FRAGMENT_PATTERNS):
        return True
    meaningful = re.sub(r"\b(?:n/?a|no|yes|over|see|endnote)\b|[\d\W_]", "", text, flags=re.I)
    return len(meaningful) < 4


def classify_oge_asset(row: Mapping[str, object]) -> str:
    asset, description = _asset_text(row)
    text = f"{asset} {description}".lower()
    if re.search(r"bitcoin|ethereum|crypto|digital asset|token", text):
        return "加密资产"
    if re.search(r"real estate|property|land|building|commercial real estate|mixed use", text):
        return "房地产/商业权益"
    if re.search(r"\b(?:llc|l\.p\.|lp|limited partnership)\b|trust|private equity|venture", text):
        return "私募/LLC/信托"
    if re.search(r"\b(?:etf|mutual fund|index fund|fund)\b", text):
        return "ETF/基金"
    if re.search(r"\b(?:treasury|municipal bond|corporate bond|fixed income|debenture)\b", text):
        return "债券"
    if re.search(r"\b(?:class [ab]|common stock|ordinary shares|inc\.?\s*\([A-Z]{1,6}\)|corp\.?\s*\([A-Z]{1,6}\))", asset, re.I):
        return "股票/上市证券"
    if re.search(r"\b(?:inc\.?|corp\.?|company|co\.?)\b", asset, re.I):
        return "公司权益/商业权益"
    return "其他资产"


def _canonical_asset(asset: str) -> str:
    text = asset.lower()
    text = re.sub(r"\b(?:n/?a|no|yes|see endnote|over \$?[\d,]+)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
        asset, _ = _asset_text(source_row)
        if _is_fragment(asset):
            continue
        key = (
            str(source_row.get("whale_name") or "").strip().lower(),
            str(source_row.get("filing_url") or source_row.get("source_id") or ""),
            _canonical_asset(asset),
        )
        if not key[2]:
            continue
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
            f"<td>{escape(classify_oge_asset(row))}</td>"
            f"<td><b>{escape(asset)}</b>"
            + (f'<br><span class="small">{escape(description[:180])}</span>' if description and description != asset else "")
            + f"</td><td>{escape(amount or '-')}</td><td>{escape(_report_date(row))}</td><td>{source_html}</td></tr>"
        )

    table = "<p>暂无通过质量校验的行政分支 OGE 资产披露。</p>" if not body else (
        "<table><thead><tr><th>人物</th><th>职位</th><th>资产类别</th><th>投资标的及简要描述</th>"
        "<th>金额/区间</th><th>披露/报告日期</th><th>来源</th></tr></thead><tbody>"
        + "".join(body) + "</tbody></table>"
    )
    return (
        '<section id="v40-cabinet-oge-radar"><h2>部长 / Cabinet OGE 披露雷达</h2>'
        '<p class="small">仅展示可识别的完整资产实体；表头、金额残片、脚注和融资条款碎片已排除。'
        '同一人物同一申报文件中的同一资产只保留一条，邮件正文最多18行。</p>' + table + "</section>"
    )
