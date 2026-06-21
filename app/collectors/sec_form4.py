from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timedelta
import json
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from app.collectors.sec_client import SecClient
from app.collectors.universe import UniverseCompany

log = logging.getLogger(__name__)

TRANSACTION_ACTIONS = {
    "P": "BUY",   # Open market/private purchase
    "S": "SELL",  # Open market/private sale
    "A": "GRANT_OR_AWARD",
    "D": "DISPOSITION_TO_ISSUER",
    "M": "OPTION_EXERCISE_OR_CONVERSION",
    "F": "TAX_WITHHOLDING_OR_PAYMENT",
    "G": "GIFT",
    "J": "OTHER",
}

HIGH_SIGNAL_CODES = {"P", "S"}




def _tag_endswith(element: ET.Element, suffix: str) -> bool:
    return element.tag.split("}")[-1] == suffix


def _find_first_text_anywhere(element: ET.Element, suffix: str) -> str:
    for child in element.iter():
        if _tag_endswith(child, suffix) and child.text:
            return child.text.strip()
    return ""


def _archive_base_from_href(href: str) -> str | None:
    # Convert filing index URLs such as
    # https://www.sec.gov/Archives/edgar/data/123/000.../index.htm
    # or -index.htm variants into the actual archive directory base.
    if not href:
        return None
    href = href.strip()
    parsed = urlparse(href)
    path = parsed.path
    match = re.search(r"(/Archives/edgar/data/\d+/\d+)", path, flags=re.IGNORECASE)
    if not match:
        return None
    return f"https://www.sec.gov{match.group(1)}"


def recent_form4_filings_from_atom(atom_text: str, lookback_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=lookback_days)
    try:
        root = ET.fromstring(atom_text)
    except ET.ParseError:
        return []

    filings: list[dict] = []
    entries = [node for node in root.iter() if _tag_endswith(node, "entry")]
    for entry in entries:
        form_type = _find_first_text_anywhere(entry, "filing-type") or _find_first_text_anywhere(entry, "category")
        if form_type and form_type != "4":
            continue
        filing_date = _find_first_text_anywhere(entry, "filing-date")
        if not filing_date:
            # The content block often contains lines like "Filing Date: 2026-06-18".
            content = " ".join((c.text or "") for c in entry.iter() if _tag_endswith(c, "content"))
            m = re.search(r"Filing Date:\s*(\d{4}-\d{2}-\d{2})", content)
            filing_date = m.group(1) if m else ""
        try:
            filing_dt = datetime.strptime(filing_date, "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            continue
        if filing_dt < cutoff:
            continue

        accession_number = _find_first_text_anywhere(entry, "accession-number")
        href = ""
        for child in entry.iter():
            if _tag_endswith(child, "link"):
                href = child.attrib.get("href", "")
                if href:
                    break
        if not href:
            content = " ".join((c.text or "") for c in entry.iter() if _tag_endswith(c, "content"))
            m = re.search(r"https://www\.sec\.gov/Archives/edgar/data/[^\s<\"]+", content)
            href = m.group(0) if m else ""
        base_url = _archive_base_from_href(href)
        if not base_url:
            continue
        filings.append(
            {
                "form": "4",
                "filing_date": filing_date,
                "accession_number": accession_number or base_url.rsplit("/", 1)[-1],
                "base_url": base_url,
                "filing_href": href,
            }
        )
    return filings

def _strip_namespace(xml_text: str) -> str:
    return re.sub(r" xmlns(:\w+)?=\"[^\"]+\"", "", xml_text, count=0)


def _text(parent: ET.Element | None, path: str, default: str = "") -> str:
    if parent is None:
        return default
    node = parent.find(path)
    if node is None or node.text is None:
        return default
    return node.text.strip()


def _float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").strip()
        if cleaned == "":
            return None
        return float(cleaned)
    except ValueError:
        return None


def _role(owner: ET.Element) -> str:
    rel = owner.find("reportingOwnerRelationship")
    if rel is None:
        return "Unknown"
    roles: list[str] = []
    if _text(rel, "isDirector") == "1":
        roles.append("Director")
    if _text(rel, "isOfficer") == "1":
        title = _text(rel, "officerTitle")
        roles.append(f"Officer: {title}" if title else "Officer")
    if _text(rel, "isTenPercentOwner") == "1":
        roles.append("10% Owner")
    if _text(rel, "isOther") == "1":
        roles.append(_text(rel, "otherText", "Other"))
    return "; ".join(roles) or "Unknown"


def _owner_category(role: str) -> str:
    role_l = role.lower()
    if "chief executive" in role_l or "ceo" in role_l:
        return "CEO"
    if "chief financial" in role_l or "cfo" in role_l:
        return "CFO"
    if "officer" in role_l:
        return "Corporate Officer"
    if "director" in role_l:
        return "Director"
    if "10%" in role_l:
        return "10% Owner"
    return "Corporate Insider"


def _owner_names(root: ET.Element) -> list[dict[str, str]]:
    owners: list[dict[str, str]] = []
    for owner in root.findall("reportingOwner"):
        name = _text(owner, "reportingOwnerId/rptOwnerName", "Unknown Owner")
        role = _role(owner)
        owners.append({"name": name, "role": role, "category": _owner_category(role)})
    if not owners:
        owners.append({"name": "Unknown Owner", "role": "Unknown", "category": "Corporate Insider"})
    return owners


def parse_form4_xml(
    xml_text: str,
    company: UniverseCompany,
    accession_number: str,
    filing_date: str,
    filing_url: str,
) -> list[dict]:
    root = ET.fromstring(_strip_namespace(xml_text))
    issuer_ticker = _text(root, "issuer/issuerTradingSymbol", company.ticker).upper().replace(".", "-")
    issuer_name = _text(root, "issuer/issuerName", company.title)
    owners = _owner_names(root)
    trades: list[dict] = []

    transaction_nodes = root.findall(".//nonDerivativeTransaction") + root.findall(".//derivativeTransaction")
    for idx, txn in enumerate(transaction_nodes):
        code = _text(txn, "transactionCoding/transactionCode", "")
        action = TRANSACTION_ACTIONS.get(code, "OTHER")
        shares = _float(_text(txn, "transactionAmounts/transactionShares/value", ""))
        price = _float(_text(txn, "transactionAmounts/transactionPricePerShare/value", ""))
        acquired_disposed = _text(txn, "transactionAmounts/transactionAcquiredDisposedCode/value", "")
        trade_date = _text(txn, "transactionDate/value", filing_date)

        # Prefer explicit A/D where code alone is ambiguous.
        if code == "P" or (code in {"A", "M"} and acquired_disposed == "A"):
            action = "BUY" if code == "P" else action
        elif code == "S" or (code in {"D", "F"} and acquired_disposed == "D"):
            action = "SELL" if code == "S" else action

        amount_usd = None
        if shares is not None and price is not None:
            amount_usd = shares * price

        raw = {
            "transaction_code": code,
            "acquired_disposed": acquired_disposed,
            "security_title": _text(txn, "securityTitle/value", ""),
            "shares_owned_following": _text(txn, "postTransactionAmounts/sharesOwnedFollowingTransaction/value", ""),
        }

        for owner in owners:
            source_id = f"SEC_FORM4:{accession_number}:{idx}:{owner['name']}:{code}:{shares}:{price}"
            trades.append(
                {
                    "source_id": source_id,
                    "ticker": issuer_ticker or company.ticker,
                    "company_name": issuer_name,
                    "cik": company.cik,
                    "accession_number": accession_number,
                    "filing_url": filing_url,
                    "whale_name": owner["name"],
                    "whale_category": owner["category"],
                    "insider_role": owner["role"],
                    "action": action,
                    "transaction_code": code,
                    "amount_usd": amount_usd,
                    "shares": shares,
                    "price": price,
                    "trade_date": trade_date,
                    "filing_date": filing_date,
                    "source": "SEC Form 4",
                    "raw_json": json.dumps(raw, ensure_ascii=False),
                }
            )
    return trades


def recent_form4_filings(submissions: dict, lookback_days: int) -> list[dict]:
    cutoff = date.today() - timedelta(days=lookback_days)
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accession_numbers = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    filings: list[dict] = []
    for i, form in enumerate(forms):
        if form != "4":
            continue
        try:
            filing_dt = datetime.strptime(filing_dates[i], "%Y-%m-%d").date()
        except Exception:  # noqa: BLE001
            continue
        if filing_dt < cutoff:
            continue
        filings.append(
            {
                "form": form,
                "filing_date": filing_dates[i],
                "accession_number": accession_numbers[i],
                "primary_document": primary_docs[i] if i < len(primary_docs) else None,
            }
        )
    return filings


def collect_sec_form4_trades(
    companies: list[UniverseCompany],
    client: SecClient,
    lookback_days: int = 3,
) -> list[dict]:
    all_trades: list[dict] = []
    companies_with_filings = 0
    filings_seen = 0
    xml_docs_seen = 0

    for n, company in enumerate(companies, start=1):
        try:
            filings: list[dict] = []

            # Primary path: issuer-level EDGAR browse feed with owner=include.
            # This is more suitable for Form 4 because the archive folder is often under
            # the reporting owner's CIK, not under the issuer's CIK.
            try:
                atom = client.browse_form4_atom(company.ticker, count=100)
                filings = recent_form4_filings_from_atom(atom, lookback_days)
            except Exception as exc:  # noqa: BLE001
                log.debug("Atom Form 4 feed failed for %s: %s", company.ticker, exc)

            # Fallback path: company submissions JSON. This may miss owner-filed Form 4 records,
            # but it keeps compatibility with environments where browse-edgar is unavailable.
            if not filings:
                try:
                    submissions = client.submissions(company.cik)
                    filings = recent_form4_filings(submissions, lookback_days)
                    for filing in filings:
                        filing["base_url"] = client.filing_base_url(company.cik, filing["accession_number"])
                except Exception as exc:  # noqa: BLE001
                    log.debug("Submissions fallback failed for %s: %s", company.ticker, exc)

            if not filings:
                continue

            companies_with_filings += 1
            filings_seen += len(filings)
            log.info("%s/%s %s has %s recent Form 4 filing(s)", n, len(companies), company.ticker, len(filings))

            for filing in filings:
                url = None
                try:
                    base_url = filing.get("base_url")
                    if base_url:
                        url = client.discover_xml_document_url_from_base(base_url)
                    if not url:
                        url = client.filing_document_url(company.cik, filing["accession_number"], filing.get("primary_document"))
                    try:
                        xml_text = client.get_text(url)
                    except Exception:  # noqa: BLE001
                        fallback = None
                        if base_url:
                            fallback = client.discover_xml_document_url_from_base(base_url)
                        if not fallback:
                            fallback = client.discover_xml_document_url(company.cik, filing["accession_number"])
                        if not fallback:
                            raise
                        url = fallback
                        xml_text = client.get_text(url)
                    xml_docs_seen += 1
                    trades = parse_form4_xml(
                        xml_text=xml_text,
                        company=company,
                        accession_number=filing["accession_number"],
                        filing_date=filing["filing_date"],
                        filing_url=url,
                    )
                    # Keep all actions for audit; the scoring engine elevates P/S.
                    all_trades.extend(trades)
                except Exception as exc:  # noqa: BLE001
                    log.warning("Could not parse Form 4 for %s accession=%s url=%s: %s", company.ticker, filing.get("accession_number"), url, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("SEC Form 4 collection failed for %s (%s): %s", company.ticker, company.cik, exc)

    log.info(
        "SEC Form 4 diagnostics: companies_scanned=%s companies_with_filings=%s filings_seen=%s xml_docs_seen=%s parsed_transactions=%s",
        len(companies), companies_with_filings, filings_seen, xml_docs_seen, len(all_trades),
    )
    return all_trades
