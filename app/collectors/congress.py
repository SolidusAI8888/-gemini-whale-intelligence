from __future__ import annotations

"""Political whale collector.

V5 adds political disclosure signals to the SEC Form 4 pipeline.

Data sources:
1. Official House Clerk yearly ZIP archive (default, no API key):
   https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip
   The ZIP contains an XML index and disclosure PDFs. We use the XML index to
   locate PTR filings and parse PDF text for stock transactions.

2. Optional Financial Modeling Prep House/Senate APIs. These endpoints are paid/restricted
   on many FMP keys. They run only when FMP_CONGRESSIONAL_ENABLED=true.
   The free/default mode relies on the official House Clerk ZIP/PDF source.

The module emits the same normalized trade schema as SEC Form 4.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from io import BytesIO
import json
import logging
import re
import time
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode
import zipfile
import xml.etree.ElementTree as ET

import requests

from app.config import settings

log = logging.getLogger(__name__)

HOUSE_ZIP_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
HOUSE_PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"
HOUSE_FINANCIAL_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}/{doc_id}.pdf"
FMP_BASE = "https://financialmodelingprep.com/stable"

TRANSACTION_WORDS = {
    "purchase": "BUY",
    "purchased": "BUY",
    "buy": "BUY",
    "sale": "SELL",
    "sold": "SELL",
    "sell": "SELL",
    "partial sale": "SELL",
    "exchange": "OTHER",
}

AMOUNT_BUCKETS = [
    ("$1,001 - $15,000", 8000),
    ("$15,001 - $50,000", 32500),
    ("$50,001 - $100,000", 75000),
    ("$100,001 - $250,000", 175000),
    ("$250,001 - $500,000", 375000),
    ("$500,001 - $1,000,000", 750000),
    ("$1,000,001 - $5,000,000", 3000000),
    ("$5,000,001 - $25,000,000", 15000000),
    ("$25,000,001 - $50,000,000", 37500000),
]

@dataclass(frozen=True)
class HouseFiling:
    doc_id: str
    filer: str
    state_district: str
    filing_type: str
    filing_date: str
    year: int
    pdf_name: str | None = None


def _headers(user_agent: str | None = None) -> dict[str, str]:
    ua = user_agent or settings.sec_user_agent or "WhaleIntelligence contact@example.com"
    return {"User-Agent": ua, "Accept": "application/json,text/html,application/pdf,*/*"}


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass
    # Try to pull an ISO-ish date from longer text.
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2}|\d{2})", text)
    if m:
        year = int(m.group(3))
        if year < 100:
            year += 2000
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def _date_str(value: Any) -> str | None:
    dt = _parse_date(value)
    return dt.isoformat() if dt else None


def _within_lookback(value: Any, cutoff: date) -> bool:
    dt = _parse_date(value)
    return bool(dt and dt >= cutoff)


def _normalize_ticker(ticker: str | None) -> str | None:
    if not ticker:
        return None
    t = ticker.upper().strip().replace(".", "-")
    t = re.sub(r"[^A-Z0-9\-]", "", t)
    if 1 <= len(t) <= 6:
        return t
    return None


def _extract_ticker(text: str, target_tickers: set[str]) -> str | None:
    """Extract a ticker from political disclosure text.

    If target_tickers is non-empty, keep only symbols in that core universe.
    If target_tickers is empty, return plausible explicit tickers. This is useful for
    POLITICAL_UNIVERSE_SCOPE=all/both diagnostics so political trades are not lost
    simply because they are outside S&P 500 / Nasdaq-100.
    """
    stop = {"PTR", "NEW", "N/A", "LLC", "INC", "ETF", "USD", "USA", "IRA", "SEP", "CBO", "CEO", "CFO", "THE", "AND", "FOR", "BUY", "SALE", "SOLD"}
    candidates = re.findall(r"\(([A-Z][A-Z0-9\.\-]{0,5})\)", text)
    candidates += re.findall(r"\bTicker[:\s]+([A-Z][A-Z0-9\.\-]{0,5})\b", text, flags=re.I)
    for c in candidates:
        t = _normalize_ticker(c)
        if t and t not in stop and (not target_tickers or t in target_tickers):
            return t
    # Last resort: scan all ticker-like tokens but only accept them when they are in
    # the target universe. In all-scope mode this is too noisy, so avoid token scan.
    if target_tickers:
        for token in re.findall(r"\b[A-Z]{1,5}\b", text):
            if token not in stop and token in target_tickers:
                return token
    return None


def _normalize_action(text: str | None) -> tuple[str, str | None]:
    raw = (text or "").strip()
    low = raw.lower()
    if re.search(r"\b(contribution|donor[-\s]?advised fund|gift)\b", low):
        return "OTHER_TRANSFER", "G"
    if re.search(r"\bp\b", low) or re.search(r"\bpurchase(?:d)?\b", low) or "purchased" in low:
        return "BUY", "P"
    if re.search(r"\bs\s*partial\b", low) or re.search(r"\bs\b", low) or re.search(r"\b(sale|sold|sell)\b", low):
        return "SELL", "S"
    for word, action in TRANSACTION_WORDS.items():
        if word in low:
            return action, "P" if action == "BUY" else "S" if action == "SELL" else None
    return "OTHER", None


def _amount_midpoint(text: Any) -> float | None:
    if text is None:
        return None
    s = str(text)
    if not s:
        return None
    for bucket, midpoint in AMOUNT_BUCKETS:
        if bucket.replace(",", "") in s.replace(",", ""):
            return float(midpoint)
    nums = [float(n.replace(",", "")) for n in re.findall(r"\$?([0-9][0-9,]*(?:\.\d+)?)", s)]
    if not nums:
        return None
    if len(nums) >= 2:
        return float((nums[0] + nums[1]) / 2)
    return float(nums[0])


def _reporting_owner_category(name: str, chamber: str) -> str:
    return f"Political Whale:{chamber}"


def _normalize_trade(
    *,
    source_id: str,
    ticker: str,
    politician: str,
    chamber: str,
    action: str,
    transaction_code: str | None,
    amount_usd: float | None,
    trade_date: str | None,
    filing_date: str | None,
    filing_url: str | None,
    raw: Mapping[str, Any] | str,
) -> dict:
    return {
        "source_id": source_id,
        "ticker": ticker,
        "company_name": None,
        "cik": None,
        "accession_number": source_id,
        "filing_url": filing_url,
        "whale_name": politician or "Unknown Political Filer",
        "whale_category": _reporting_owner_category(politician, chamber),
        "insider_role": chamber,
        "action": action,
        "transaction_code": transaction_code,
        "amount_usd": amount_usd,
        "shares": None,
        "price": None,
        "trade_date": trade_date,
        "filing_date": filing_date,
        "source": f"POLITICAL_{chamber.upper()}",
        "raw_json": json.dumps(raw, ensure_ascii=False) if not isinstance(raw, str) else raw,
    }


def _download_house_zip(year: int, user_agent: str) -> zipfile.ZipFile | None:
    url = HOUSE_ZIP_URL.format(year=year)
    try:
        response = requests.get(url, headers=_headers(user_agent), timeout=60)
        response.raise_for_status()
        return zipfile.ZipFile(BytesIO(response.content))
    except Exception as exc:  # noqa: BLE001
        log.warning("House ZIP download failed for %s: %s", year, exc)
        return None


def _find_xml_name(zf: zipfile.ZipFile, year: int) -> str | None:
    names = zf.namelist()
    preferred = f"{year}FD.xml"
    if preferred in names:
        return preferred
    for name in names:
        if name.lower().endswith(".xml"):
            return name
    return None


def _node_text(node: ET.Element, *names: str) -> str:
    lookup = {child.tag.lower(): (child.text or "").strip() for child in list(node)}
    for name in names:
        value = lookup.get(name.lower())
        if value:
            return value
    return ""


def _house_filings_from_zip(zf: zipfile.ZipFile, year: int, cutoff: date) -> list[HouseFiling]:
    xml_name = _find_xml_name(zf, year)
    if not xml_name:
        return []
    root = ET.fromstring(zf.read(xml_name))
    filings: list[HouseFiling] = []
    # The XML structure varies slightly by year; treat every leaf-ish element with a DocID as a filing.
    for node in root.iter():
        doc_id = _node_text(node, "DocID", "DocumentID", "DocId")
        filing_type = _node_text(node, "FilingType", "Filing Type", "Type")
        if not doc_id or filing_type.upper() != "P":
            continue
        filing_date = _node_text(node, "FilingDate", "Filing Date", "Date")
        if filing_date and not _within_lookback(filing_date, cutoff):
            continue
        first = _node_text(node, "First", "FirstName", "First Name")
        last = _node_text(node, "Last", "LastName", "Last Name")
        filer = _node_text(node, "Member", "Filer", "Name") or " ".join(x for x in [first, last] if x).strip()
        state_dst = _node_text(node, "StateDst", "State District", "District")
        pdf_name = None
        for name in zf.namelist():
            base = name.rsplit("/", 1)[-1]
            if base == f"{doc_id}.pdf":
                pdf_name = name
                break
        filings.append(HouseFiling(doc_id=doc_id, filer=filer, state_district=state_dst, filing_type=filing_type, filing_date=_date_str(filing_date) or date(year, 1, 1).isoformat(), year=year, pdf_name=pdf_name))
    return filings


def _extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        log.warning("House PDF text extraction failed: %s", exc)
        return ""


def _download_house_pdf(doc_id: str, year: int, user_agent: str) -> tuple[bytes | None, str | None]:
    for url in (HOUSE_PTR_PDF_URL.format(year=year, doc_id=doc_id), HOUSE_FINANCIAL_PDF_URL.format(year=year, doc_id=doc_id)):
        try:
            response = requests.get(url, headers=_headers(user_agent), timeout=45)
            if response.status_code == 200 and response.content.startswith(b"%PDF"):
                return response.content, url
        except Exception:  # noqa: BLE001
            continue
    return None, None



def _all_dates(text: str) -> list[date]:
    dates: list[date] = []
    for m in re.finditer(r"(\d{1,2}/\d{1,2}/(?:20\d{2}|\d{2})|20\d{2}[-/]\d{1,2}[-/]\d{1,2})", text or ""):
        dt = _parse_date(m.group(1))
        if dt:
            dates.append(dt)
    return dates


def _select_house_transaction_date(window: str, filing_date: str | None) -> str | None:
    dates = _all_dates(window)
    if not dates:
        return filing_date
    filing_dt = _parse_date(filing_date) or date.today()
    # House PTR option descriptions include an expiration date after the transaction
    # date.  Prefer the first date that is not after the filing date + 45 days; this
    # keeps 05/29/2026 and rejects 03/19/2027 expiration dates.
    max_trade_date = filing_dt + timedelta(days=45)
    for dt in dates:
        if dt <= max_trade_date:
            return dt.isoformat()
    return dates[0].isoformat()


def _extract_house_option_metadata(window: str) -> dict[str, Any]:
    raw = window or ""
    low = raw.lower()
    out: dict[str, Any] = {}
    if "[op]" in low or "call option" in low or "put option" in low or "option" in low:
        out["asset_type"] = "Option"
    if "call option" in low:
        out["option_type"] = "Call"
    elif "put option" in low:
        out["option_type"] = "Put"
    m = re.search(r"(?:purchased|sold|sale of|purchase of)?\s*([0-9][0-9,]*)\s+(?:call|put)?\s*options?", raw, re.I)
    if m:
        try:
            out["contracts"] = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    m = re.search(r"strike(?:\s+price)?\s*(?:of|=|:)??\s*\$?\s*([0-9]+(?:\.[0-9]+)?)", raw, re.I)
    if m:
        try:
            out["strike"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"expiration(?:\s+date)?\s*(?:of|=|:)??\s*(\d{1,2}/\d{1,2}/(?:20\d{2}|\d{2}))", raw, re.I)
    if m:
        out["expiration_date"] = _date_str(m.group(1))
    if re.search(r"donor[-\s]?advised fund|contribution", raw, re.I):
        out["transfer_type"] = "Donor-Advised Fund / Contribution"
    return out


def _house_candidate_windows(lines: list[str]) -> list[tuple[int, str]]:
    candidates: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        low = line.lower()
        has_ticker = bool(re.search(r"\([A-Z][A-Z0-9.\-]{0,5}\)\s*(?:\[[A-Z]{2}\])?", line))
        has_action = any(word in low for word in ("purchase", "purchased", "sale", "sold", "exchange", "s partial", "donor-advised", "contribution")) or line.strip().upper() in {"P", "S", "S PARTIAL"}
        if not (has_ticker or has_action):
            continue
        # Wide window so rows split across separate asset/ticker/action/date/amount lines
        # are reconstructed.  This fixes Pelosi PTR rows such as INTC/UBER options.
        start = max(0, idx - 2)
        end = min(len(lines), idx + 9)
        candidates.append((idx, " ".join(lines[start:end])))
    return candidates

def _parse_house_pdf_transactions(filing: HouseFiling, pdf_text: str, pdf_url: str, target_tickers: set[str]) -> list[dict]:
    trades: list[dict] = []
    if not pdf_text:
        return trades
    # Collapse page noise while keeping enough context per line.
    lines = [re.sub(r"\s+", " ", line).strip() for line in pdf_text.splitlines()]
    lines = [line for line in lines if line]
    seen: set[tuple] = set()
    for idx, window in _house_candidate_windows(lines):
        ticker = _extract_ticker(window, target_tickers)
        if not ticker:
            continue
        action, code = _normalize_action(window)
        if action not in {"BUY", "SELL", "OTHER_TRANSFER"}:
            continue
        tx_date = _select_house_transaction_date(window, filing.filing_date) or filing.filing_date
        amount = _amount_midpoint(window)
        option_meta = _extract_house_option_metadata(window)
        # Avoid turning the option expiration date into the trade date.
        if option_meta.get("expiration_date") and tx_date == option_meta.get("expiration_date"):
            tx_date = filing.filing_date
        dedup_key = (filing.doc_id, ticker, action, tx_date, amount, option_meta.get("contracts"), option_meta.get("strike"), option_meta.get("expiration_date"))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        source_id = f"HOUSE:{filing.doc_id}:{ticker}:{action}:{tx_date}:{amount or 0}:{option_meta.get('contracts','')}:{option_meta.get('expiration_date','')}"
        raw = {"doc_id": filing.doc_id, "context": window, **option_meta}
        trades.append(
            _normalize_trade(
                source_id=source_id,
                ticker=ticker,
                politician=filing.filer,
                chamber="House",
                action=action,
                transaction_code=code,
                amount_usd=amount,
                trade_date=tx_date,
                filing_date=filing.filing_date,
                filing_url=pdf_url,
                raw=raw,
            )
        )
    return trades


def collect_house_trades_official(target_tickers: set[str], user_agent: str, lookback_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=lookback_days)
    years = sorted({cutoff.year, date.today().year})
    results: list[dict] = []
    filings_seen = 0
    pdfs_parsed = 0
    for year in years:
        zf = _download_house_zip(year, user_agent)
        if not zf:
            continue
        filings = _house_filings_from_zip(zf, year, cutoff)
        filings_seen += len(filings)
        log.info("House official PTR filings in lookback for %s: %s", year, len(filings))
        for filing in filings[: settings.political_max_filings]:
            pdf_data = None
            pdf_url = None
            if filing.pdf_name:
                try:
                    pdf_data = zf.read(filing.pdf_name)
                    pdf_url = HOUSE_PTR_PDF_URL.format(year=year, doc_id=filing.doc_id)
                except Exception:  # noqa: BLE001
                    pdf_data = None
            if not pdf_data:
                pdf_data, pdf_url = _download_house_pdf(filing.doc_id, year, user_agent)
            if not pdf_data or not pdf_url:
                continue
            pdfs_parsed += 1
            text = _extract_pdf_text(pdf_data)
            results.extend(_parse_house_pdf_transactions(filing, text, pdf_url, target_tickers))
            time.sleep(0.1)
    log.info("Political House official diagnostics: filings_seen=%s pdfs_parsed=%s trades=%s", filings_seen, pdfs_parsed, len(results))
    return results


def _get_first(row: Mapping[str, Any], *names: str) -> Any:
    lower = {str(k).lower(): v for k, v in row.items()}
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
        value = lower.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _collect_fmp_endpoint(endpoint: str, chamber: str, target_tickers: set[str], lookback_days: int) -> list[dict]:
    api_key = settings.fmp_api_key
    if not api_key:
        return []
    cutoff = date.today() - timedelta(days=lookback_days)
    out: list[dict] = []
    for page in range(max(settings.fmp_max_pages, 1)):
        params = {"page": page, "limit": settings.fmp_page_limit, "apikey": api_key}
        url = f"{FMP_BASE}/{endpoint}?{urlencode(params)}"
        try:
            response = requests.get(url, headers=_headers(), timeout=45)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("FMP %s page %s failed: %s", endpoint, page, exc)
            break
        if isinstance(data, dict):
            rows = data.get("data") or data.get("results") or data.get("items") or []
        else:
            rows = data
        if not rows:
            break
        for i, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            symbol = _normalize_ticker(str(_get_first(row, "symbol", "ticker") or ""))
            asset = str(_get_first(row, "assetDescription", "asset", "asset_name", "security", "description") or "")
            if not symbol:
                symbol = _extract_ticker(asset, target_tickers)
            if target_tickers and symbol not in target_tickers:
                continue
            transaction_date = _date_str(_get_first(row, "transactionDate", "transaction_date", "transaction_date_formatted", "date"))
            filing_date = _date_str(_get_first(row, "disclosureDate", "filingDate", "filedDate", "filing_date", "publishedDate")) or transaction_date
            if filing_date and not _within_lookback(filing_date, cutoff):
                continue
            action_raw = _get_first(row, "type", "transactionType", "transaction_type", "transaction")
            action, code = _normalize_action(str(action_raw or ""))
            if action not in {"BUY", "SELL"}:
                continue
            politician = str(_get_first(row, "representative", "senator", "name", "member", "politician") or "Unknown")
            amount = _amount_midpoint(_get_first(row, "amount", "amountRange", "range", "value"))
            filing_url = str(_get_first(row, "link", "url", "filingUrl", "disclosureUrl") or "") or None
            sid_base = _get_first(row, "id", "docID", "documentId", "disclosureId") or f"{page}:{i}"
            source_id = f"FMP_{chamber.upper()}:{sid_base}:{symbol}:{action}:{transaction_date}:{amount or 0}"
            out.append(
                _normalize_trade(
                    source_id=source_id,
                    ticker=symbol,
                    politician=politician,
                    chamber=chamber,
                    action=action,
                    transaction_code=code,
                    amount_usd=amount,
                    trade_date=transaction_date,
                    filing_date=filing_date,
                    filing_url=filing_url,
                    raw=row,
                )
            )
        if len(rows) < settings.fmp_page_limit:
            break
    log.info("FMP %s political trades normalized: %s", chamber, len(out))
    return out


def _split_csv(value: str) -> list[str]:
    return [x.strip() for x in (value or "").split(",") if x.strip()]


def _collect_fmp_by_name_endpoint(endpoint: str, chamber: str, name: str, target_tickers: set[str], lookback_days: int) -> list[dict]:
    """Collect FMP congressional trades by politician name.

    FMP exposes endpoints such as senate-trades-by-name?name=Jerry. These are
    especially useful for watchlist names such as Pelosi/Trump because the
    latest feed can page past a specific person quickly.
    """
    api_key = settings.fmp_api_key
    if not api_key or not name:
        return []
    cutoff = date.today() - timedelta(days=lookback_days)
    out: list[dict] = []
    for page in range(max(settings.fmp_max_pages, 1)):
        params = {"name": name, "page": page, "limit": settings.fmp_page_limit, "apikey": api_key}
        url = f"{FMP_BASE}/{endpoint}?{urlencode(params)}"
        try:
            response = requests.get(url, headers=_headers(), timeout=45)
            if response.status_code in {401, 402, 403}:
                log.warning("FMP %s by-name endpoint appears unavailable for this key: status=%s body=%s", endpoint, response.status_code, response.text[:300])
                break
            response.raise_for_status()
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            log.warning("FMP %s name=%s page=%s failed: %s", endpoint, name, page, exc)
            break
        rows = data.get("data") if isinstance(data, dict) else data
        if isinstance(data, dict):
            rows = data.get("data") or data.get("results") or data.get("items") or []
        if not rows:
            break
        for i, row in enumerate(rows):
            if not isinstance(row, Mapping):
                continue
            symbol = _normalize_ticker(str(_get_first(row, "symbol", "ticker") or ""))
            asset = str(_get_first(row, "assetDescription", "asset", "asset_name", "security", "description") or "")
            if not symbol:
                symbol = _extract_ticker(asset, target_tickers)
            # In all/both scope, keep non-core tickers if explicitly present. In core scope, filter.
            if target_tickers and settings.political_universe_scope == "core" and symbol not in target_tickers:
                continue
            if not symbol:
                continue
            transaction_date = _date_str(_get_first(row, "transactionDate", "transaction_date", "transaction_date_formatted", "date"))
            filing_date = _date_str(_get_first(row, "disclosureDate", "filingDate", "filedDate", "filing_date", "publishedDate")) or transaction_date
            if filing_date and not _within_lookback(filing_date, cutoff):
                continue
            action_raw = _get_first(row, "type", "transactionType", "transaction_type", "transaction")
            action, code = _normalize_action(str(action_raw or ""))
            if action not in {"BUY", "SELL"}:
                continue
            politician = str(_get_first(row, "representative", "senator", "name", "member", "politician") or name)
            amount = _amount_midpoint(_get_first(row, "amount", "amountRange", "range", "value"))
            filing_url = str(_get_first(row, "link", "url", "filingUrl", "disclosureUrl") or "") or None
            sid_base = _get_first(row, "id", "docID", "documentId", "disclosureId") or f"{name}:{page}:{i}"
            source_id = f"FMP_{chamber.upper()}_NAME:{sid_base}:{symbol}:{action}:{transaction_date}:{amount or 0}"
            out.append(_normalize_trade(source_id=source_id, ticker=symbol, politician=politician, chamber=chamber, action=action, transaction_code=code, amount_usd=amount, trade_date=transaction_date, filing_date=filing_date, filing_url=filing_url, raw=row))
        if len(rows) < settings.fmp_page_limit:
            break
    log.info("FMP %s by-name political trades normalized for %s: %s", chamber, name, len(out))
    return out


def collect_fmp_congress_trades(target_tickers: set[str], lookback_days: int) -> list[dict]:
    if not settings.fmp_congressional_enabled:
        log.info("FMP congressional APIs disabled: FMP_CONGRESSIONAL_ENABLED=false. Using free official House source only.")
        return []
    if not settings.fmp_api_key:
        log.info("FMP_API_KEY not set; skipping optional FMP House/Senate political APIs")
        return []

    trades: list[dict] = []
    house_endpoints = _split_csv(settings.fmp_house_endpoints) or ["house-latest"]
    senate_endpoints = _split_csv(settings.fmp_senate_endpoints) or ["senate-latest"]
    log.info("FMP congressional endpoints: house=%s senate=%s scope=%s watch_names=%s", house_endpoints, senate_endpoints, settings.political_universe_scope, settings.political_watch_names)

    for endpoint in house_endpoints:
        if endpoint.endswith("-by-name"):
            continue
        trades.extend(_collect_fmp_endpoint(endpoint, "House", target_tickers, lookback_days))
    for endpoint in senate_endpoints:
        if endpoint.endswith("-by-name"):
            continue
        trades.extend(_collect_fmp_endpoint(endpoint, "Senate", target_tickers, lookback_days))

    # Always query by-name endpoints for watchlist names, independent of latest-feed paging.
    watch_names = _split_csv(settings.political_watch_names)
    for name in watch_names:
        trades.extend(_collect_fmp_by_name_endpoint("house-trades-by-name", "House", name, target_tickers, lookback_days))
        trades.extend(_collect_fmp_by_name_endpoint("senate-trades-by-name", "Senate", name, target_tickers, lookback_days))

    log.info("FMP congressional trades total before provider de-dupe: %s", len(trades))
    return trades


def collect_congress_trades(target_tickers: Iterable[str] | None = None, user_agent: str | None = None, lookback_days: int | None = None) -> list[dict]:
    """Collect political whale trades and normalize to the common schema."""
    if not settings.enable_political_trades:
        log.info("ENABLE_POLITICAL_TRADES=false; skipping political collector")
        return []
    tickers = {str(t).upper() for t in (target_tickers or []) if t}
    scope = settings.political_universe_scope
    if not tickers and scope == "core":
        log.warning("Political collector skipped because target_tickers is empty and POLITICAL_UNIVERSE_SCOPE=core")
        return []
    if not tickers:
        log.info("Political collector running without core ticker filter because POLITICAL_UNIVERSE_SCOPE=%s", scope)
    ua = user_agent or settings.sec_user_agent
    days = lookback_days or settings.lookback_days
    trades: list[dict] = []
    provider = settings.political_provider.lower().strip()
    if provider in {"auto", "official_house", "house"}:
        trades.extend(collect_house_trades_official(tickers, ua, days))
    if provider in {"auto", "fmp"}:
        trades.extend(collect_fmp_congress_trades(tickers, days))
    # Dedupe across official/FMP providers.
    dedup: dict[str, dict] = {}
    for trade in trades:
        dedup[trade["source_id"]] = trade
    out = list(dedup.values())
    if tickers:
        matched = sum(1 for t in out if str(t.get("ticker", "")).upper() in tickers)
        off = len(out) - matched
        log.info("Political trades collected after de-duplication: %s; core_universe=%s; off_universe=%s; scope=%s", len(out), matched, off, scope)
    else:
        log.info("Political trades collected after de-duplication: %s; scope=%s", len(out), scope)
    return out
