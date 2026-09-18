from __future__ import annotations

"""House annual-disclosure holdings.

Annual Schedule A rows are snapshots, not transactions.  Only explicit stock
rows (asset code ``ST``) enter the holdings surface; options and other assets
remain outside the stock-holding view.
"""

from datetime import date, datetime
import hashlib
import io
import json
import logging
import re

import requests
from pypdf import PdfReader

log = logging.getLogger(__name__)


HOUSE_ANNUAL_REPORTS = (
    (
        "Nancy Pelosi",
        "Member, U.S. House of Representatives",
        "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2025/10075701.pdf",
    ),
)

_ROW_RE = re.compile(
    r"^(?P<asset>.+?)\s+\((?P<ticker>[A-Z][A-Z0-9.\-]{0,7})\)\s+"
    r"\[ST\]\s+(?P<owner>SP|JT|DC)\s+\$(?P<low>[\d,]+)\s*-\s*(?:\$(?P<high>[\d,]+))?$",
    re.I,
)
_HIGH_RE = re.compile(r"^\$(?P<high>[\d,]+)$")


def parse_house_annual_holdings(
    text: str,
    *,
    filer_name: str,
    role: str,
    source_url: str,
) -> list[dict]:
    filing = re.search(r"Filing Date:\s*(\d{2}/\d{2}/\d{4})", text or "", re.I)
    filing_date = date.today().isoformat()
    if filing:
        filing_date = datetime.strptime(filing.group(1), "%m/%d/%Y").date().isoformat()

    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines()]
    rows: list[dict] = []
    for index, line in enumerate(lines):
        match = _ROW_RE.match(line)
        if not match:
            continue
        high = match.group("high")
        if not high and index + 1 < len(lines):
            continuation = _HIGH_RE.match(lines[index + 1])
            high = continuation.group("high") if continuation else None
        if not high:
            continue
        low_value = float(match.group("low").replace(",", ""))
        high_value = float(high.replace(",", ""))
        if high_value < low_value:
            continue
        raw_ticker = match.group("ticker").upper()
        ticker = "GOOG" if raw_ticker in {"GOOG", "GOOGL"} else raw_ticker
        asset = match.group("asset").strip()
        owner = match.group("owner").upper()
        midpoint = (low_value + high_value) / 2
        amount_label = f"${low_value:,.0f}–${high_value:,.0f}"
        raw = {
            "report_type": "HOUSE_ANNUAL_FINANCIAL_DISCLOSURE",
            "asset_name": asset,
            "asset_code": "ST",
            "owner": owner,
            "reported_ticker": raw_ticker,
            "amount_low": low_value,
            "amount_high": high_value,
            "amount_mid": midpoint,
            "amount_range_label": amount_label,
            "radar_note": "Annual Schedule A stock holding; not a BUY/SELL transaction",
        }
        source_id = "HOUSEHOLDING:" + hashlib.sha256(
            f"{source_url}|{filer_name}|{ticker}|{owner}|{asset}|{amount_label}".encode()
        ).hexdigest()[:28]
        rows.append({
            "source_id": source_id,
            "ticker": ticker,
            "company_name": asset,
            "cik": None,
            "accession_number": None,
            "filing_url": source_url,
            "whale_name": filer_name,
            "whale_category": "Political:House",
            "insider_role": role,
            "action": "HOLDING",
            "transaction_code": "H",
            "amount_usd": midpoint,
            "shares": None,
            "price": None,
            "trade_date": filing_date,
            "filing_date": filing_date,
            "source": "POLITICAL_HOUSE_HOLDING",
            "raw_json": json.dumps(raw, ensure_ascii=False),
        })
    return rows


def collect_house_annual_holdings(user_agent: str, lookback_days: int) -> list[dict]:
    cutoff = date.today().toordinal() - max(int(lookback_days or 365), 1)
    output: list[dict] = []
    for filer, role, url in HOUSE_ANNUAL_REPORTS:
        try:
            response = requests.get(url, headers={"User-Agent": user_agent}, timeout=90)
            response.raise_for_status()
            reader = PdfReader(io.BytesIO(response.content))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            rows = parse_house_annual_holdings(text, filer_name=filer, role=role, source_url=url)
            output.extend(row for row in rows if datetime.fromisoformat(row["filing_date"]).date().toordinal() >= cutoff)
        except Exception as exc:  # noqa: BLE001 - one unavailable filing must not abort a scan
            log.warning("House annual holding collection failed for %s: %s", filer, exc)
    return output
