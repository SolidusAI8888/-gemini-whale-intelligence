from __future__ import annotations

import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable
from urllib.parse import urljoin

from app.config import settings

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstitutionalWhale:
    manager: str
    cik: str
    lead_investor: str
    style: str = "Institutional whale"


# Expert-style default active/influential institutional whale watchlist.
# We intentionally avoid pure passive index giants and favor concentrated,
# activist, event-driven, value, technology-growth and multi-strategy managers
# whose 13F changes are commonly watched by market participants.
DEFAULT_INSTITUTIONAL_WHALES: tuple[InstitutionalWhale, ...] = (
    InstitutionalWhale("Berkshire Hathaway", "1067983", "Warren Buffett", "Long-term value/quality"),
    InstitutionalWhale("Pershing Square Capital Management", "1336528", "Bill Ackman", "Concentrated activist/value"),
    InstitutionalWhale("Appaloosa LP", "1656456", "David Tepper", "Opportunistic value/macro"),
    InstitutionalWhale("Third Point LLC", "1040273", "Dan Loeb", "Event-driven/activist"),
    InstitutionalWhale("Baupost Group", "1061768", "Seth Klarman", "Value/special situations"),
    InstitutionalWhale("Greenlight Capital", "1079114", "David Einhorn", "Value/long-short"),
    InstitutionalWhale("Scion Asset Management", "1649339", "Michael Burry", "Contrarian/special situations"),
    InstitutionalWhale("Duquesne Family Office", "1536411", "Stanley Druckenmiller", "Macro/growth"),
    InstitutionalWhale("Soros Fund Management", "1029160", "Soros family office", "Macro/event-driven"),
    InstitutionalWhale("Coatue Management", "1135730", "Philippe Laffont", "Technology growth"),
    InstitutionalWhale("Tiger Global Management", "1167483", "Chase Coleman", "Technology growth"),
    InstitutionalWhale("Lone Pine Capital", "1061165", "Stephen Mandel lineage", "Growth/quality"),
    InstitutionalWhale("D1 Capital Partners", "1747057", "Dan Sundheim", "Crossover/growth"),
    InstitutionalWhale("Viking Global Investors", "1103804", "Andreas Halvorsen", "Long-short/quality"),
    InstitutionalWhale("Maverick Capital", "936944", "Lee Ainslie", "Long-short growth"),
    InstitutionalWhale("Point72 Asset Management", "1603466", "Steve Cohen", "Multi-strategy"),
    InstitutionalWhale("Bridgewater Associates", "1350694", "Ray Dalio legacy", "Macro/systematic"),
    InstitutionalWhale("Elliott Investment Management", "1048445", "Paul Singer", "Activist/event-driven"),
    InstitutionalWhale("Icahn Capital", "921669", "Carl Icahn", "Activist"),
    InstitutionalWhale("Trian Fund Management", "1345471", "Nelson Peltz", "Activist"),
)

# Minimal issuer-name map to make the most important high-interest rows readable
# even when the 13F information table omits ticker tags and only provides issuer
# names/CUSIP. The raw issuer/CUSIP remains in raw_json for verification.
ISSUER_TICKER_HINTS = {
    "UBER TECHNOLOGIES": "UBER",
    "APPLE INC": "AAPL",
    "AMAZON COM INC": "AMZN",
    "ALPHABET INC": "GOOGL",
    "MICROSOFT CORP": "MSFT",
    "META PLATFORMS": "META",
    "NVIDIA CORP": "NVDA",
    "BROADCOM INC": "AVGO",
    "TESLA INC": "TSLA",
    "CHIPOTLE MEXICAN": "CMG",
    "HILTON WORLDWIDE": "HLT",
    "RESTAURANT BRANDS": "QSR",
    "HOWARD HUGHES": "HHH",
    "BROOKFIELD CORP": "BN",
    "CANADIAN PACIFIC": "CP",
}


def _http_get(url: str, user_agent: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - public SEC URLs only
        return resp.read()


def _txt(el: ET.Element, local_name: str) -> str:
    for child in el.iter():
        if child.tag.split("}")[-1] == local_name:
            return (child.text or "").strip()
    return ""


def _parse_watchlist(raw: str | None = None) -> list[InstitutionalWhale]:
    text = (raw if raw is not None else settings.institutional_13f_watchlist).strip()
    if not text:
        return list(DEFAULT_INSTITUTIONAL_WHALES)
    out: list[InstitutionalWhale] = []
    for line in re.split(r"[\n;]+", text):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        manager, cik = parts[0], re.sub(r"\D", "", parts[1])
        lead = parts[2] if len(parts) > 2 and parts[2] else manager
        style = parts[3] if len(parts) > 3 and parts[3] else "Institutional whale"
        if manager and cik:
            out.append(InstitutionalWhale(manager, cik, lead, style))
    return out or list(DEFAULT_INSTITUTIONAL_WHALES)


def _recent_13f_filings(cik: str, user_agent: str, max_filings: int = 2) -> list[dict]:
    cik10 = cik.zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
    try:
        data = json.loads(_http_get(url, user_agent).decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        log.warning("13F submissions fetch failed manager_cik=%s error=%s", cik, exc)
        return []
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    report_dates = recent.get("reportDate", [])
    rows = []
    for form, acc, filed, report in zip(forms, accessions, filing_dates, report_dates):
        if str(form).upper() in {"13F-HR", "13F-HR/A"}:
            rows.append({"form": form, "accession": acc, "filing_date": filed, "report_date": report})
        if len(rows) >= max_filings:
            break
    return rows


def _filing_files(cik: str, accession: str, user_agent: str) -> list[str]:
    cik_nolead = str(int(cik))
    acc_nodash = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_nolead}/{acc_nodash}/"
    try:
        data = json.loads(_http_get(urljoin(base, "index.json"), user_agent).decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        log.warning("13F filing index fetch failed cik=%s accession=%s error=%s", cik, accession, exc)
        return []
    names = [item.get("name", "") for item in data.get("directory", {}).get("item", [])]
    return [urljoin(base, n) for n in names if n]


def _pick_info_table(files: Iterable[str]) -> str | None:
    candidates = []
    for url in files:
        name = url.rsplit("/", 1)[-1].lower()
        if not name.endswith((".xml", ".txt")):
            continue
        score = 0
        if "infotable" in name or "info_table" in name or "form13f" in name:
            score += 10
        if name.endswith(".xml"):
            score += 3
        candidates.append((score, url))
    if not candidates:
        return None
    return sorted(candidates, reverse=True)[0][1]


def _infer_ticker(issuer: str, ticker_tag: str, cusip: str) -> str:
    tag = re.sub(r"[^A-Za-z0-9.-]", "", ticker_tag or "").upper()
    if tag and tag not in {"COM", "SH", "CL", "CLASS"}:
        return tag[:12]
    upper = re.sub(r"\s+", " ", issuer.upper())
    for key, ticker in ISSUER_TICKER_HINTS.items():
        if key in upper:
            return ticker
    return f"CUSIP:{cusip}" if cusip else upper[:12].replace(" ", "_") or "UNKNOWN"


def _parse_info_table(xml_bytes: bytes, whale: InstitutionalWhale, filing: dict, info_url: str, max_rows: int) -> list[dict]:
    text = xml_bytes.decode("utf-8", errors="replace")
    # Some filers put XML inside a text submission; trim to informationTable if needed.
    start = text.find("<informationTable")
    if start >= 0:
        text = text[start:]
        end = text.rfind("</informationTable>")
        if end >= 0:
            text = text[: end + len("</informationTable>")]
    try:
        root = ET.fromstring(text.encode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("13F info table parse failed manager=%s accession=%s error=%s", whale.manager, filing.get("accession"), exc)
        return []
    rows: list[dict] = []
    for table in root.iter():
        if table.tag.split("}")[-1] != "infoTable":
            continue
        issuer = _txt(table, "nameOfIssuer")
        cusip = _txt(table, "cusip")
        ticker = _infer_ticker(issuer, _txt(table, "ticker"), cusip)
        value_thousands = 0.0
        try:
            value_thousands = float((_txt(table, "value") or "0").replace(",", ""))
        except Exception:  # noqa: BLE001
            pass
        shares = 0.0
        try:
            shares = float((_txt(table, "sshPrnamt") or "0").replace(",", ""))
        except Exception:  # noqa: BLE001
            pass
        # SEC 13F "value" is normally reported in thousands of USD.
        # Some modern/third-party normalized XMLs may already expose a dollar
        # value.  A blind *1000 then creates impossible trillion-dollar single
        # positions for active managers such as Pershing/Tiger.  Normalize with
        # a conservative sanity check: if the converted single position exceeds
        # $500B, treat the source value as already dollars.
        amount = value_thousands * 1000
        value_unit = "thousands_usd"
        if amount > 500_000_000_000:
            amount = value_thousands
            value_unit = "usd_normalized"
        if amount <= 0 and shares <= 0:
            continue
        report_date = str(filing.get("report_date") or "")[:10]
        filing_date = str(filing.get("filing_date") or "")[:10]
        source_id = f"13F:{whale.cik}:{filing.get('accession')}:{cusip or issuer}:{ticker}"
        raw = {
            "report_type": "13F-HR",
            "manager": whale.manager,
            "lead_investor": whale.lead_investor,
            "style": whale.style,
            "nameOfIssuer": issuer,
            "cusip": cusip,
            "titleOfClass": _txt(table, "titleOfClass"),
            "putCall": _txt(table, "putCall"),
            "value_reported": value_thousands,
            "value_unit": value_unit,
            "value_thousands_usd": value_thousands if value_unit == "thousands_usd" else None,
            "share_amount": shares,
            "report_period": report_date,
            "filing_date": filing_date,
            "note": "13F quarterly holding disclosure; not a real-time trade date.",
        }
        rows.append({
            "source_id": source_id,
            "ticker": ticker,
            "company_name": issuer or ticker,
            "cik": whale.cik,
            "accession_number": filing.get("accession"),
            "filing_url": info_url,
            "whale_name": whale.lead_investor,
            "whale_category": "Institutional 13F",
            "insider_role": whale.manager,
            "action": "HOLDING_13F",
            "transaction_code": "13F",
            "amount_usd": amount,
            "shares": shares,
            "price": None,
            "trade_date": report_date,
            "filing_date": filing_date,
            "source": "INSTITUTIONAL_13F",
            "raw_json": json.dumps(raw, ensure_ascii=False),
        })
        if len(rows) >= max_rows:
            break
    return sorted(rows, key=lambda r: float(r.get("amount_usd") or 0), reverse=True)


def collect_institutional_13f_holdings(user_agent: str, lookback_days: int = 370) -> list[dict]:
    if not settings.enable_institutional_13f:
        return []
    cutoff = date.today() - timedelta(days=max(int(lookback_days or 370), 1))
    rows: list[dict] = []
    whales = _parse_watchlist()[: settings.institutional_13f_max_managers]
    for whale in whales:
        filings = _recent_13f_filings(whale.cik, user_agent, max_filings=settings.institutional_13f_filings_per_manager)
        for filing in filings:
            try:
                fd = date.fromisoformat(str(filing.get("filing_date") or "1900-01-01")[:10])
            except Exception:  # noqa: BLE001
                fd = date(1900, 1, 1)
            if fd < cutoff:
                continue
            files = _filing_files(whale.cik, str(filing.get("accession") or ""), user_agent)
            info_url = _pick_info_table(files)
            if not info_url:
                continue
            try:
                xml_bytes = _http_get(info_url, user_agent)
            except Exception as exc:  # noqa: BLE001
                log.warning("13F info table fetch failed manager=%s url=%s error=%s", whale.manager, info_url, exc)
                continue
            parsed = _parse_info_table(xml_bytes, whale, filing, info_url, max_rows=settings.institutional_13f_max_holdings_per_filing)
            rows.extend(parsed)
            log.info("13F parsed manager=%s accession=%s rows=%s", whale.manager, filing.get("accession"), len(parsed))
    log.info("13F institutional holdings collected: %s", len(rows))
    return rows


# Test hooks
def parse_13f_info_table_for_tests(xml_text: str, manager: str = "Pershing Square Capital Management", cik: str = "1336528") -> list[dict]:
    whale = InstitutionalWhale(manager, cik, "Bill Ackman", "Concentrated activist/value")
    filing = {"accession": "0000000000-26-000001", "filing_date": "2026-05-15", "report_date": "2026-03-31"}
    return _parse_info_table(xml_text.encode("utf-8"), whale, filing, "https://example.com/infoTable.xml", 20)
