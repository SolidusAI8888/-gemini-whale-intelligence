from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import logging
import re
from urllib.parse import urlparse, urljoin, unquote
from typing import Iterable

import requests
from pypdf import PdfReader

from app.config import settings

log = logging.getLogger(__name__)

AMOUNT_RANGE_RE = re.compile(
    r"\$?([0-9][0-9,]*(?:\.\d+)?)\s*(?:-|to|–|—)\s*\$?([0-9][0-9,]*(?:\.\d+)?)",
    re.I,
)
MONEY_RE = re.compile(r"\$\s*([0-9][0-9,]*(?:\.\d+)?)")
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{1,2}-\d{1,2})\b")
TICKER_RE = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,7})\)")
SYMBOL_RE = re.compile(r"\b(?:ticker|symbol)\s*[:#\-]?\s*([A-Z][A-Z0-9.\-]{0,7})\b", re.I)
KNOWN_TICKERS = {
    "microsoft": "MSFT",
    "meta platforms": "META",
    "facebook": "META",
    "amazon": "AMZN",
    "nvidia": "NVDA",
    "advanced micro devices": "AMD",
    "oracle": "ORCL",
    "apple": "AAPL",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "tesla": "TSLA",
    "netflix": "NFLX",
    "broadcom": "AVGO",
}

OGE_STANDARD_RANGES = [
    (1001, 15000),
    (15001, 50000),
    (50001, 100000),
    (100001, 250000),
    (250001, 500000),
    (500001, 1000000),
    (1000001, 5000000),
    (5000001, 25000000),
    (25000001, 50000000),
]

ACTIONS = {
    "purchase": ("BUY", "P"),
    "buy": ("BUY", "P"),
    "sale": ("SELL", "S"),
    "sell": ("SELL", "S"),
    "sold": ("SELL", "S"),
    "exchange": ("EXCHANGE", "E"),
}


def _parse_date(value: str) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_money_num(value: str) -> float:
    return float(value.replace(",", ""))


def _repair_oge_range(lo: float, hi: float) -> tuple[float, float, str | None]:
    """Repair common OGE PDF text-extraction truncations and validate ranges.

    OGE 278-T values are reported in fixed buckets.  PDF extraction sometimes
    turns "$1,000,001 - $5,000,000" into "$1 - $5,000,000", or
    "$1,001 - $15,000" into "$1,001 - $15".  We only repair values that map
    unambiguously to an official bucket; otherwise the row is quarantined by
    returning midpoint None upstream.
    """
    original = (lo, hi)
    # Repair truncated upper thousands/millions, e.g. 15 -> 15,000.
    if hi < lo and hi in {15, 50, 100, 250, 500, 1000, 5000, 25000, 50000}:
        hi *= 1000
    # Repair first-term truncation by matching the bucket upper bound.
    if lo in {1, 1001} or (lo < 1000 and hi >= 15000):
        for std_lo, std_hi in OGE_STANDARD_RANGES:
            if abs(hi - std_hi) < 0.01:
                lo = float(std_lo)
                break
    # Accept exact official OGE buckets only.
    for std_lo, std_hi in OGE_STANDARD_RANGES:
        if abs(lo - std_lo) < 0.01 and abs(hi - std_hi) < 0.01:
            warning = None if original == (lo, hi) else f"repaired_range_from_{original[0]:.0f}_{original[1]:.0f}"
            return float(std_lo), float(std_hi), warning
    return lo, hi, "non_standard_amount_range"


def _parse_amount_range(text: str) -> tuple[float | None, float | None, float | None, str | None, str | None]:
    clean = " ".join((text or "").replace("\u2013", "-").replace("\u2014", "-").split())
    m = AMOUNT_RANGE_RE.search(clean)
    if m:
        lo = _parse_money_num(m.group(1))
        hi = _parse_money_num(m.group(2))
        lo, hi, warning = _repair_oge_range(lo, hi)
        if warning == "non_standard_amount_range":
            return None, None, None, f"${lo:,.0f}–${hi:,.0f}", warning
        return lo, hi, (lo + hi) / 2.0, f"${lo:,.0f}–${hi:,.0f}", warning
    over = re.search(r"(?:over|greater than|more than)\s+\$\s*([0-9][0-9,]*(?:\.\d+)?)", clean, re.I)
    if over:
        lo = _parse_money_num(over.group(1))
        return lo, None, lo, f">${lo:,.0f}", None
    # Single-money extraction is too ambiguous for OGE ranges and is often an
    # OCR fragment, so keep it out of normalized scoring.
    monies = MONEY_RE.findall(clean)
    if monies:
        val = _parse_money_num(monies[-1])
        return None, None, None, f"${val:,.0f}", "single_amount_fragment"
    return None, None, None, None, "missing_amount"


def _clean_oge_trade_date(raw_date: str | None, filing_date: str | None, block: str) -> tuple[str | None, str | None]:
    """Correct or quarantine impossible OGE transaction dates.

    Trump's 2026 OGE PDF extraction has been observed to read 2026 as 2028.
    When a date is in the future but replacing year-2 produces a plausible
    non-future date, we correct it and flag the correction.  Otherwise the row
    is quarantined by returning None.
    """
    if not raw_date:
        return raw_date, None
    try:
        d = datetime.strptime(raw_date, "%Y-%m-%d").date()
    except ValueError:
        return raw_date, "invalid_date"
    today = date.today()
    filing_dt = None
    if filing_date:
        try:
            filing_dt = datetime.strptime(filing_date, "%Y-%m-%d").date()
        except ValueError:
            filing_dt = None
    max_allowed = max([x for x in [today + timedelta(days=30), filing_dt + timedelta(days=30) if filing_dt else None] if x])
    if d <= max_allowed:
        return d.isoformat(), None
    # Common OCR error: 2026 -> 2028.
    candidate = date(d.year - 2, d.month, d.day) if d.year - 2 >= 2020 else None
    if candidate and candidate <= max_allowed:
        return candidate.isoformat(), f"corrected_future_date_from_{d.isoformat()}"
    return None, f"future_date_quarantined_{d.isoformat()}"


def _normalize_action(text: str) -> tuple[str | None, str | None]:
    lower = (text or "").lower()
    # OGE PDFs are often OCR/extracted imperfectly: purchase can appear as
    # "purd'lase", "purch ase", etc.  Treat common fragments defensively.
    compact = re.sub(r"[^a-z]+", "", lower)
    if re.search(r"\bexchange\b", lower):
        return ACTIONS["exchange"]
    if re.search(r"\b(sale|sell|sold)\b", lower) or "sale" in compact or "sold" in compact:
        return ACTIONS["sale"]
    if re.search(r"\b(purchase|buy|bought)\b", lower) or "purch" in compact or "purchase" in compact or "bought" in compact:
        return ACTIONS["purchase"]
    return None, None


def _looks_like_trade_block(text: str) -> bool:
    action, _ = _normalize_action(text)
    if not action:
        return False
    # Must look like a dated row with a disclosed amount/range.  Ticker is optional
    # at this stage because many OGE rows do not use Form-4 style "(MSFT)" text.
    return bool(DATE_RE.search(text) and (AMOUNT_RANGE_RE.search(text) or MONEY_RE.search(text)))


def _extract_ticker(block: str) -> str | None:
    m = TICKER_RE.search(block)
    if m:
        candidate = m.group(1).replace(".", "-").upper()
        # Avoid treating bond ratings / common form labels as stock tickers.
        if candidate not in {"B", "C", "D", "E", "B/E", "B-C", "A", "N/A"}:
            return candidate
    m = SYMBOL_RE.search(block)
    if m:
        return m.group(1).replace(".", "-").upper()
    lower = block.lower()
    for key, ticker in KNOWN_TICKERS.items():
        if key in lower:
            return ticker
    return None


def _asset_name_from_block(block: str, ticker: str) -> str:
    before = block.split(f"({ticker})", 1)[0]
    before = re.sub(r"^.*?(?:Asset|Name|Description)\s*[:\-]?\s*", "", before, flags=re.I)
    before = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b.*$", "", before)
    name = before.strip(" -:;|\t")
    if len(name) > 120:
        name = name[-120:].strip()
    return name or ticker


def _pdf_text_from_url(url: str, user_agent: str) -> str:
    resp = requests.get(
        url,
        headers={"User-Agent": user_agent, "Accept": "application/pdf,*/*"},
        timeout=90,
    )
    log.info(
        "OGE PDF fetch: url=%s status=%s content_type=%s bytes=%s",
        _mask_url(url),
        resp.status_code,
        resp.headers.get("content-type", ""),
        len(resp.content or b""),
    )
    resp.raise_for_status()
    reader = PdfReader(io.BytesIO(resp.content))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to extract OGE PDF page text: %s", exc)
    text = "\n".join(pages)
    log.info("OGE PDF extracted: pages=%s text_chars=%s", len(reader.pages), len(text))
    return text


def _blocks_from_text(text: str) -> list[str]:
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in (text or "").splitlines()]
    lines = [ln for ln in lines if ln]
    blocks: list[str] = []
    # Prefer individual extracted lines when they already contain a complete row.
    for line in lines:
        if _looks_like_trade_block(line):
            blocks.append(line)
    # If a PDF row is split across lines, also inspect short windows, but do not
    # add a window that merely combines already-complete adjacent rows.
    for idx, line in enumerate(lines):
        window_lines = lines[idx : idx + 4]
        if any(_looks_like_trade_block(ln) for ln in window_lines):
            continue
        window = " ".join(window_lines)
        if _looks_like_trade_block(window):
            blocks.append(window)
    # Keep full rows/windows.  Exact duplicate parser windows are removed below.
    extra: list[str] = [b for b in blocks if _looks_like_trade_block(b)]
    # De-duplicate exact parser windows.
    seen = set()
    out = []
    for b in extra:
        key = b.lower()
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out


def _parse_trade_blocks(
    *,
    text: str,
    filer_name: str,
    position: str,
    agency: str,
    source_url: str,
    report_type: str = "OGE_278_T",
) -> list[dict]:
    late_fee = bool(re.search(r"late fee|late fees|filer paid late", text, re.I))
    discretionary = bool(re.search(r"discretionary|independent\s+(?:manager|advisor)|investment\s+(?:manager|advisor)|managed account|trust", text, re.I))
    today = date.today().isoformat()
    rows: list[dict] = []
    for block in _blocks_from_text(text):
        ticker = _extract_ticker(block)
        if not ticker:
            continue
        action, code = _normalize_action(block)
        if not action or not code:
            continue
        dates = [_parse_date(m.group(1)) for m in DATE_RE.finditer(block)]
        dates = [d for d in dates if d]
        trade_date = dates[0] if dates else None
        filing_date = dates[-1] if len(dates) > 1 else today
        trade_date, date_warning = _clean_oge_trade_date(trade_date, filing_date, block)
        amount_low, amount_high, amount_mid, amount_label, amount_warning = _parse_amount_range(block)
        if not trade_date or amount_mid is None:
            log.info(
                "OGE parser quarantined row: ticker=%s date_warning=%s amount_warning=%s block=%s",
                ticker,
                date_warning,
                amount_warning,
                block[:240],
            )
            continue
        asset_name = _asset_name_from_block(block, ticker)
        raw = {
            "report_type": report_type,
            "filer_name": filer_name,
            "position": position,
            "agency": agency,
            "asset_name": asset_name,
            "amount_low": amount_low,
            "amount_high": amount_high,
            "amount_mid": amount_mid,
            "amount_range_label": amount_label,
            "late_fee_flag": late_fee,
            "discretionary_account_flag": discretionary,
            "source_url": source_url,
            "parser_block": block,
            "date_parse_warning": date_warning,
            "amount_parse_warning": amount_warning,
            "parse_status": "repaired" if (date_warning or amount_warning) else "ok",
        }
        source_id = "OGE:" + hashlib.sha256(
            f"{source_url}|{filer_name}|{ticker}|{action}|{trade_date}|{amount_label}|{asset_name}".encode("utf-8")
        ).hexdigest()[:28]
        category = "Executive:President" if "president" in position.lower() else "Executive:Cabinet"
        source = "OGE_EXECUTIVE_TRUMP" if category == "Executive:President" else "OGE_EXECUTIVE_CABINET"
        rows.append(
            {
                "source_id": source_id,
                "ticker": ticker,
                "company_name": asset_name,
                "cik": None,
                "accession_number": None,
                "filing_url": source_url,
                "whale_name": filer_name,
                "whale_category": category,
                "insider_role": position or agency or category,
                "action": action,
                "transaction_code": code,
                "amount_usd": float(amount_mid),
                "shares": None,
                "price": None,
                "trade_date": trade_date,
                "filing_date": filing_date,
                "source": source,
                "raw_json": json.dumps(raw, ensure_ascii=False),
            }
        )
    return rows


@dataclass(frozen=True)
class ExecutiveReportSpec:
    name: str
    position: str
    agency: str
    url: str
    report_type: str = "OGE_278_T"


def _split_urls(value: str) -> list[str]:
    # URLs can legally contain commas in filenames (e.g. "Trump, Donald J.").
    # Only semicolon and newline are supported as separators.
    return [x.strip() for x in re.split(r"[;\n]+", value or "") if x.strip()]


def _mask_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        tail = parsed.path.rsplit("/", 1)[-1]
        return f"{parsed.netloc}/.../{tail[:80]}"
    except Exception:
        return "<unparseable-url>"


def _cabinet_specs(value: str) -> list[ExecutiveReportSpec]:
    specs: list[ExecutiveReportSpec] = []
    for item in re.split(r"\n|;", value or ""):
        item = item.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split("|")]
        if len(parts) >= 3:
            name, position, url = parts[0], parts[1], parts[2]
            agency = parts[3] if len(parts) >= 4 else position
            report_type = parts[4] if len(parts) >= 5 else _infer_report_type_from_text(url, item)
            specs.append(ExecutiveReportSpec(name=name, position=position, agency=agency, url=url, report_type=report_type))
        else:
            log.warning("Skipping malformed OGE_CABINET_REPORTS entry: %s", item)
    return specs


SEEDED_CABINET_REPORTS = [
    # Official OGE PDFs from extapps2.oge.gov. These are not secrets; they are
    # public disclosure documents.  They give the Cabinet radar immediate coverage
    # while the OGE search-page discovery remains best-effort.
    ExecutiveReportSpec(
        "Scott Bessent",
        "Secretary of the Treasury",
        "Treasury",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/BA716BA5B423A76685258CE6002C8303/%24FILE/Scott-Bessent-07.14.2025-278T.pdf",
        "OGE_278_T",
    ),
    ExecutiveReportSpec(
        "Howard Lutnick",
        "Secretary of Commerce",
        "Commerce",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/66A69EB879848CF885258CC9002C8582/%24FILE/Howard-Lutnick-06.17.2025-278T.pdf",
        "OGE_278_T",
    ),
    ExecutiveReportSpec(
        "Howard Lutnick",
        "Secretary of Commerce",
        "Commerce",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/8C12E5475578E84385258D5C00345940/%24FILE/Howard-Lutnick-11.05.2025-278T.pdf",
        "OGE_278_T",
    ),
    ExecutiveReportSpec(
        "Chris Wright",
        "Secretary of Energy",
        "Energy",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/5057175949E7195F85258C70002C8C7C/%24FILE/Christopher-A-Wright-03.19.2025-278T.pdf",
        "OGE_278_T",
    ),
    ExecutiveReportSpec(
        "Chris Wright",
        "Secretary of Energy",
        "Energy",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/22F95E0EAFBF6F1D85258DCC002DDF75/%24FILE/Christopher-A-Wright-01.13.2026-278T.pdf",
        "OGE_278_T",
    ),
    ExecutiveReportSpec(
        "Doug Burgum",
        "Secretary of the Interior",
        "Interior",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/3742068B59ECA5BC85258C130032E5E3/%24FILE/Burgum%2C%20Doug%20%20final278.pdf",
        "OGE_278e",
    ),
    ExecutiveReportSpec(
        "Howard Lutnick",
        "Secretary of Commerce",
        "Commerce",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/AC841CF0E3B5807A85258C1C00320D21/%24FILE/Lutnick%2C%20Howard%20%20final278.pdf",
        "OGE_278e",
    ),
    ExecutiveReportSpec(
        "Chris Wright",
        "Secretary of Energy",
        "Energy",
        "https://extapps2.oge.gov/201/Presiden.nsf/PAS%2BIndex/3743C3A1AEA32F4385258C150032F2B6/%24FILE/Wright%2C%20Christopher%20Allen%20%20final278.pdf",
        "OGE_278e",
    ),
]


def _seeded_cabinet_specs() -> list[ExecutiveReportSpec]:
    specs = list(SEEDED_CABINET_REPORTS) if settings.oge_seed_cabinet_reports_enabled else []
    specs.extend(_cabinet_specs(settings.oge_seed_cabinet_reports))
    return specs


def _infer_report_type_from_text(url: str, context: str = "") -> str:
    text = unquote(" ".join([url or "", context or ""])).lower()
    if re.search(r"278\s*[-_ ]?t|278t|transaction", text):
        return "OGE_278_T"
    if re.search(r"ethics agreement|finalea|\bea\b", text):
        return "OGE_ETHICS_AGREEMENT"
    if re.search(r"certificate of divestiture|divestiture|cd\b", text):
        return "OGE_DIVESTITURE"
    if re.search(r"278e|final278|public financial disclosure|financial disclosure", text):
        return "OGE_278e"
    return "OGE_278e"


def _name_tokens(name: str) -> set[str]:
    cleaned = re.sub(r"[^A-Za-z\s.-]", " ", name or "")
    parts = [p.strip().lower() for p in re.split(r"\s+", cleaned) if len(p.strip()) >= 3]
    return set(parts)


def _infer_spec_from_url(url: str, context: str, default_position: str = "Executive Branch Watchlist") -> ExecutiveReportSpec | None:
    text = unquote(" ".join([url, context or ""]))
    report_type = _infer_report_type_from_text(url, context)
    # V19 discovers both transaction reports and asset/ethics files.  Only
    # 278-T rows enter trading charts; 278e/Ethics rows feed the Cabinet asset radar.
    if report_type not in {"OGE_278_T", "OGE_278e", "OGE_ETHICS_AGREEMENT", "OGE_DIVESTITURE"}:
        return None
    watch_names = [x.strip() for x in re.split(r"[,;\n]+", settings.oge_discovery_watchlist or settings.oge_executive_watchlist or "") if x.strip()]
    lower = text.lower()
    matched_name = None
    for name in watch_names:
        tokens = _name_tokens(name)
        if not tokens:
            continue
        if name.lower() in lower or any(tok in lower for tok in sorted(tokens, key=len, reverse=True)[:1]):
            matched_name = name
            break
    if not matched_name:
        tail = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        m = re.match(r"([A-Za-z]+)[,\-\s]+([A-Za-z.]+).*", tail, re.I)
        if m and not re.search(r"^(final|report|ethics|certificate)$", m.group(1), re.I):
            matched_name = f"{m.group(1)} {m.group(2)}".replace("-", " ").strip()
    if not matched_name:
        return None
    position = "President" if "trump" in matched_name.lower() else default_position
    agency = "White House" if position == "President" else "Executive Branch"
    return ExecutiveReportSpec(name=matched_name, position=position, agency=agency, url=url, report_type=report_type)


def _discover_oge_specs(user_agent: str) -> list[ExecutiveReportSpec]:
    if not settings.enable_oge_auto_discovery:
        log.info("OGE auto-discovery disabled")
        return []
    urls = _split_urls(settings.oge_discovery_urls)
    if not urls:
        return []
    found: dict[str, ExecutiveReportSpec] = {}
    for page_url in urls:
        try:
            log.info("OGE discovery fetch: %s", _mask_url(page_url))
            resp = requests.get(page_url, headers={"User-Agent": user_agent, "Accept": "text/html,*/*"}, timeout=45)
            log.info("OGE discovery page status=%s bytes=%s", resp.status_code, len(resp.content or b""))
            resp.raise_for_status()
            html = resp.text or ""
        except Exception as exc:  # noqa: BLE001
            log.warning("OGE discovery failed for %s: %s", _mask_url(page_url), exc)
            continue
        # Keep anchor text context near each href. This covers direct extapps2 PDF links
        # and OGE pages exposing $FILE PDF URLs.
        for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
            href = m.group(1).replace("&amp;", "&")
            label = re.sub(r"<[^>]+>", " ", m.group(2))
            full = urljoin(page_url, href)
            if not ("%24FILE" in full or "$FILE" in full or full.lower().endswith(".pdf") or "extapps2.oge.gov" in full.lower()):
                continue
            spec = _infer_spec_from_url(full, label)
            if spec:
                found[spec.url] = spec
                if len(found) >= max(settings.oge_discovery_max_links, 1):
                    break
        # Some OGE pages include bare URLs not wrapped in anchors.
        for raw in re.findall(r'https?://[^\s"\'<>]+', html, re.I):
            full = raw.replace("&amp;", "&")
            if not ("%24FILE" in full or "$FILE" in full or full.lower().endswith(".pdf") or "extapps2.oge.gov" in full.lower()):
                continue
            spec = _infer_spec_from_url(full, full)
            if spec:
                found[spec.url] = spec
                if len(found) >= max(settings.oge_discovery_max_links, 1):
                    break
    log.info("OGE discovery specs found: %s", len(found))
    for spec in found.values():
        log.info("OGE discovery candidate: %s / %s / %s", spec.name, spec.position, _mask_url(spec.url))
    return list(found.values())


def _filing_date_from_text(text: str) -> str:
    # Use the latest plausible signature/review date in the first pages as the
    # disclosure date for non-transaction OGE documents.
    dates = [_parse_date(m.group(1)) for m in DATE_RE.finditer(text or "")]
    parsed = []
    for d in dates:
        if not d:
            continue
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            if 2024 <= dt.year <= date.today().year + 1:
                parsed.append(dt)
        except ValueError:
            continue
    if parsed:
        return max(parsed).isoformat()
    return date.today().isoformat()


def _asset_slug(asset: str) -> str:
    ticker = _extract_ticker(asset or "")
    if ticker:
        return ticker
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", asset or "OGE-ASSET").strip("-").upper()
    if not cleaned:
        return "OGE-ASSET"
    return ("OGE-" + cleaned[:18]).strip("-")


def _clean_asset_description(line: str) -> str:
    line = re.sub(r"\$?([0-9][0-9,]*(?:\.\d+)?)\s*(?:-|to|–|—)\s*\$?([0-9][0-9,]*(?:\.\d+)?)", " ", line)
    line = DATE_RE.sub(" ", line)
    line = re.sub(r"\b(?:value|income|type|amount|assets? and income|description|name)\b", " ", line, flags=re.I)
    line = re.sub(r"\s+", " ", line).strip(" -:;|\t")
    return line[:180]


def _looks_like_asset_line(line: str) -> bool:
    if _looks_like_trade_block(line):
        return False
    if not (AMOUNT_RANGE_RE.search(line) or MONEY_RE.search(line)):
        return False
    lower = line.lower()
    noise = [
        "agency ethics", "office of government ethics", "signature", "electronically signed",
        "page ", "filing status", "committee on", "comments of reviewing", "reporting status",
    ]
    if any(x in lower for x in noise):
        return False
    # Require some alphabetic content that looks like an asset/entity name.
    return len(re.sub(r"[^a-zA-Z]", "", line)) >= 5


def _parse_asset_disclosure_blocks(
    *,
    text: str,
    filer_name: str,
    position: str,
    agency: str,
    source_url: str,
    report_type: str,
    max_rows: int = 80,
) -> list[dict]:
    """Best-effort 278e/Ethics asset radar parser.

    It does not treat 278e assets as trades.  Rows use action=HOLDING and feed
    only the Cabinet asset radar, not BUY/SELL charts or scoring.
    """
    if not settings.enable_oge_asset_disclosures:
        return []
    filing_date = _filing_date_from_text(text)
    lines = [re.sub(r"\s+", " ", ln).strip() for ln in (text or "").splitlines()]
    candidates: list[str] = []
    for idx, line in enumerate(lines):
        if not line:
            continue
        windows = [line, " ".join(lines[idx: idx + 2]), " ".join(lines[idx: idx + 3])]
        for w in windows:
            if _looks_like_asset_line(w):
                candidates.append(w)
                break
    rows = []
    seen = set()
    for block in candidates:
        amount_low, amount_high, amount_mid, amount_label, amount_warning = _parse_amount_range(block)
        if amount_mid is None:
            continue
        asset_name = _clean_asset_description(block)
        if not asset_name or len(asset_name) < 3:
            continue
        key = (asset_name.lower(), amount_label)
        if key in seen:
            continue
        seen.add(key)
        ticker = _asset_slug(asset_name)
        raw = {
            "report_type": report_type,
            "filer_name": filer_name,
            "position": position,
            "agency": agency,
            "asset_name": asset_name,
            "amount_low": amount_low,
            "amount_high": amount_high,
            "amount_mid": amount_mid,
            "amount_range_label": amount_label,
            "source_url": source_url,
            "parser_block": block,
            "parse_status": "asset_radar",
            "amount_parse_warning": amount_warning,
            "radar_note": "278e/Ethics asset disclosure; not a recent BUY/SELL trade",
        }
        source_id = "OGEASSET:" + hashlib.sha256(
            f"{source_url}|{filer_name}|{ticker}|{filing_date}|{amount_label}|{asset_name}".encode("utf-8")
        ).hexdigest()[:28]
        rows.append({
            "source_id": source_id,
            "ticker": ticker,
            "company_name": asset_name,
            "cik": None,
            "accession_number": None,
            "filing_url": source_url,
            "whale_name": filer_name,
            "whale_category": "Executive:Cabinet",
            "insider_role": position or agency or "Executive Branch",
            "action": "HOLDING",
            "transaction_code": "H",
            "amount_usd": float(amount_mid),
            "shares": None,
            "price": None,
            "trade_date": filing_date,
            "filing_date": filing_date,
            "source": "OGE_EXECUTIVE_ASSET",
            "raw_json": json.dumps(raw, ensure_ascii=False),
        })
        if len(rows) >= max_rows:
            break
    if not rows:
        # Preserve discovery status even when a 278e/Ethics PDF has no reliable
        # asset rows in text extraction.
        raw = {
            "report_type": report_type,
            "filer_name": filer_name,
            "position": position,
            "agency": agency,
            "asset_name": f"{report_type} document discovered; no asset rows parsed",
            "amount_range_label": "未解析",
            "source_url": source_url,
            "parse_status": "document_found_no_asset_rows",
        }
        source_id = "OGEDOC:" + hashlib.sha256(f"{source_url}|{filer_name}|{report_type}".encode("utf-8")).hexdigest()[:28]
        rows.append({
            "source_id": source_id,
            "ticker": "OGE-DOC",
            "company_name": raw["asset_name"],
            "cik": None,
            "accession_number": None,
            "filing_url": source_url,
            "whale_name": filer_name,
            "whale_category": "Executive:Cabinet",
            "insider_role": position or agency or "Executive Branch",
            "action": "DISCLOSURE",
            "transaction_code": "D",
            "amount_usd": 0.0,
            "shares": None,
            "price": None,
            "trade_date": filing_date,
            "filing_date": filing_date,
            "source": "OGE_EXECUTIVE_ASSET",
            "raw_json": json.dumps(raw, ensure_ascii=False),
        })
    return rows


def collect_oge_executive_trades(user_agent: str, lookback_days: int) -> list[dict]:
    """Collect OGE executive branch 278-T transactions from configured PDF URLs.

    Official OGE search pages are human-facing and may not expose stable API URLs.
    This collector is therefore intentionally URL-driven: configure official OGE
    or OGE-hosted PDF URLs in OGE_TRUMP_REPORT_URLS and OGE_CABINET_REPORTS.
    """
    if not settings.enable_oge_executive_trades:
        log.info("OGE executive collector disabled")
        return []

    trump_urls = _split_urls(settings.oge_trump_report_urls)
    cabinet_specs = _cabinet_specs(settings.oge_cabinet_reports)
    seeded_specs = _seeded_cabinet_specs()
    discovered_specs = _discover_oge_specs(user_agent)
    log.info(
        "OGE executive config: enabled=%s trump_url_present=%s trump_url_count=%s cabinet_spec_count=%s seeded_spec_count=%s discovery_enabled=%s discovered_count=%s max_reports=%s",
        settings.enable_oge_executive_trades,
        bool(settings.oge_trump_report_urls),
        len(trump_urls),
        len(cabinet_specs),
        len(seeded_specs),
        settings.enable_oge_auto_discovery,
        len(discovered_specs),
        settings.oge_max_reports,
    )
    for idx, url in enumerate(trump_urls, 1):
        log.info("OGE Trump URL %s/%s: %s", idx, len(trump_urls), _mask_url(url))

    specs: list[ExecutiveReportSpec] = []
    for url in trump_urls:
        specs.append(
            ExecutiveReportSpec(
                name=settings.oge_trump_filer_name,
                position="President",
                agency="White House",
                url=url,
                report_type="OGE_278_T",
            )
        )
    specs.extend(cabinet_specs)
    specs.extend(seeded_specs)
    # Auto-discovered reports are appended after explicitly configured URLs so
    # manual Trump/Cabinet PDFs remain deterministic and first in processing.
    seen_urls = {spec.url for spec in specs}
    for spec in discovered_specs:
        if spec.url not in seen_urls:
            specs.append(spec)
            seen_urls.add(spec.url)
    if not specs:
        log.info("OGE executive collector enabled but no report URLs configured")
        return []

    cutoff = date.today() - timedelta(days=max(int(lookback_days or 365), 1))
    all_rows: list[dict] = []
    for spec in specs[: max(settings.oge_max_reports, 1)]:
        try:
            log.info("Fetching OGE executive report: %s / %s", spec.name, spec.url)
            text = _pdf_text_from_url(spec.url, user_agent)
            parser_blocks = _blocks_from_text(text)
            log.info("OGE parser candidate blocks for %s: %s report_type=%s", spec.name, len(parser_blocks), spec.report_type)
            rows = []
            if spec.report_type == "OGE_278_T":
                rows.extend(_parse_trade_blocks(
                    text=text,
                    filer_name=spec.name,
                    position=spec.position,
                    agency=spec.agency,
                    source_url=spec.url,
                    report_type=spec.report_type,
                ))
            else:
                rows.extend(_parse_asset_disclosure_blocks(
                    text=text,
                    filer_name=spec.name,
                    position=spec.position,
                    agency=spec.agency,
                    source_url=spec.url,
                    report_type=spec.report_type,
                ))
            filtered = []
            for row in rows:
                try:
                    d = datetime.strptime(str(row.get("trade_date") or row.get("filing_date")), "%Y-%m-%d").date()
                    if d < cutoff:
                        continue
                except Exception:  # noqa: BLE001
                    pass
                filtered.append(row)
            log.info("OGE executive normalized trades for %s: raw=%s filtered=%s", spec.name, len(rows), len(filtered))
            all_rows.extend(filtered)
        except Exception as exc:  # noqa: BLE001
            log.warning("OGE executive report failed for %s: %s", spec.name, exc)
    log.info("OGE executive trades collected: %s", len(all_rows))
    return all_rows


# Expose parser helpers for tests without network.
parse_oge_text_for_tests = _parse_trade_blocks
parse_oge_asset_text_for_tests = _parse_asset_disclosure_blocks
