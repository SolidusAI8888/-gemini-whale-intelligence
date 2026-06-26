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
            specs.append(ExecutiveReportSpec(name=name, position=position, agency=agency, url=url))
        else:
            log.warning("Skipping malformed OGE_CABINET_REPORTS entry: %s", item)
    return specs



def _name_tokens(name: str) -> set[str]:
    cleaned = re.sub(r"[^A-Za-z\s.-]", " ", name or "")
    parts = [p.strip().lower() for p in re.split(r"\s+", cleaned) if len(p.strip()) >= 3]
    return set(parts)


def _infer_spec_from_url(url: str, context: str, default_position: str = "Executive Branch Watchlist") -> ExecutiveReportSpec | None:
    text = unquote(" ".join([url, context or ""]))
    # Restrict auto-discovery to transaction reports; 278e asset disclosures need a
    # different parser and should not be treated as new trades.
    if not re.search(r"278\s*T|278T|Transaction", text, re.I):
        return None
    watch_names = [x.strip() for x in re.split(r"[,;\n]+", settings.oge_discovery_watchlist or settings.oge_executive_watchlist or "") if x.strip()]
    lower = text.lower()
    matched_name = None
    for name in watch_names:
        tokens = _name_tokens(name)
        if not tokens:
            continue
        # Prefer exact full-name match, otherwise require the surname/last token.
        if name.lower() in lower or any(tok in lower for tok in sorted(tokens, key=len, reverse=True)[:1]):
            matched_name = name
            break
    if not matched_name:
        # Try filename patterns like Scott-Bessent-07.14.2025-278T.pdf.
        tail = unquote(urlparse(url).path.rsplit("/", 1)[-1])
        m = re.match(r"([A-Za-z]+)[,\-\s]+([A-Za-z.]+).*278\s*T", tail, re.I)
        if m:
            matched_name = f"{m.group(1)} {m.group(2)}".replace("-", " ").strip()
    if not matched_name:
        return None
    position = "President" if "trump" in matched_name.lower() else default_position
    agency = "White House" if position == "President" else "Executive Branch"
    return ExecutiveReportSpec(name=matched_name, position=position, agency=agency, url=url)


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
    discovered_specs = _discover_oge_specs(user_agent)
    log.info(
        "OGE executive config: enabled=%s trump_url_present=%s trump_url_count=%s cabinet_spec_count=%s discovery_enabled=%s discovered_count=%s max_reports=%s",
        settings.enable_oge_executive_trades,
        bool(settings.oge_trump_report_urls),
        len(trump_urls),
        len(cabinet_specs),
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
            )
        )
    specs.extend(cabinet_specs)
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
            log.info("OGE parser candidate blocks for %s: %s", spec.name, len(parser_blocks))
            rows = _parse_trade_blocks(
                text=text,
                filer_name=spec.name,
                position=spec.position,
                agency=spec.agency,
                source_url=spec.url,
            )
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
