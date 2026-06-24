from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import logging
import re
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


def _parse_amount_range(text: str) -> tuple[float | None, float | None, float | None, str | None]:
    clean = " ".join((text or "").replace("\u2013", "-").replace("\u2014", "-").split())
    m = AMOUNT_RANGE_RE.search(clean)
    if m:
        lo = _parse_money_num(m.group(1))
        hi = _parse_money_num(m.group(2))
        # OGE range labels normally omit the $ in the second term after extraction.
        return lo, hi, (lo + hi) / 2.0, f"${lo:,.0f}–${hi:,.0f}"
    over = re.search(r"(?:over|greater than|more than)\s+\$\s*([0-9][0-9,]*(?:\.\d+)?)", clean, re.I)
    if over:
        lo = _parse_money_num(over.group(1))
        return lo, None, lo, f">${lo:,.0f}"
    monies = MONEY_RE.findall(clean)
    if monies:
        val = _parse_money_num(monies[-1])
        return val, val, val, f"${val:,.0f}"
    return None, None, None, None


def _normalize_action(text: str) -> tuple[str | None, str | None]:
    lower = (text or "").lower()
    # Prefer sale before sell, purchase before buy; avoid matching asset names by using word boundaries.
    for word in ("purchase", "sale", "exchange", "buy", "sell", "sold"):
        if re.search(rf"\b{re.escape(word)}\b", lower):
            return ACTIONS[word]
    return None, None


def _looks_like_trade_block(text: str) -> bool:
    if not TICKER_RE.search(text):
        return False
    action, _ = _normalize_action(text)
    if not action:
        return False
    return bool(DATE_RE.search(text))


def _asset_name_from_block(block: str, ticker: str) -> str:
    before = block.split(f"({ticker})", 1)[0]
    before = re.sub(r"^.*?(?:Asset|Name|Description)\s*[:\-]?\s*", "", before, flags=re.I)
    before = re.sub(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b.*$", "", before)
    name = before.strip(" -:;|\t")
    if len(name) > 120:
        name = name[-120:].strip()
    return name or ticker


def _pdf_text_from_url(url: str, user_agent: str) -> str:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=60)
    resp.raise_for_status()
    reader = PdfReader(io.BytesIO(resp.content))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            log.warning("Failed to extract OGE PDF page text: %s", exc)
    return "\n".join(pages)


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
        ticker_m = TICKER_RE.search(block)
        if not ticker_m:
            continue
        ticker = ticker_m.group(1).replace(".", "-").upper()
        action, code = _normalize_action(block)
        if not action or not code:
            continue
        dates = [_parse_date(m.group(1)) for m in DATE_RE.finditer(block)]
        dates = [d for d in dates if d]
        trade_date = dates[0] if dates else None
        filing_date = dates[-1] if len(dates) > 1 else today
        amount_low, amount_high, amount_mid, amount_label = _parse_amount_range(block)
        if amount_mid is None:
            # OGE 278-T reports use broad amount ranges.  Rows without an amount
            # are kept out of the scoring store to avoid false signals.
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
    return [x.strip() for x in re.split(r"[,\n;]+", value or "") if x.strip()]


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


def collect_oge_executive_trades(user_agent: str, lookback_days: int) -> list[dict]:
    """Collect OGE executive branch 278-T transactions from configured PDF URLs.

    Official OGE search pages are human-facing and may not expose stable API URLs.
    This collector is therefore intentionally URL-driven: configure official OGE
    or OGE-hosted PDF URLs in OGE_TRUMP_REPORT_URLS and OGE_CABINET_REPORTS.
    """
    if not settings.enable_oge_executive_trades:
        log.info("OGE executive collector disabled")
        return []

    specs: list[ExecutiveReportSpec] = []
    for url in _split_urls(settings.oge_trump_report_urls):
        specs.append(
            ExecutiveReportSpec(
                name=settings.oge_trump_filer_name,
                position="President",
                agency="White House",
                url=url,
            )
        )
    specs.extend(_cabinet_specs(settings.oge_cabinet_reports))
    if not specs:
        log.info("OGE executive collector enabled but no report URLs configured")
        return []

    cutoff = date.today() - timedelta(days=max(int(lookback_days or 365), 1))
    all_rows: list[dict] = []
    for spec in specs[: max(settings.oge_max_reports, 1)]:
        try:
            log.info("Fetching OGE executive report: %s / %s", spec.name, spec.url)
            text = _pdf_text_from_url(spec.url, user_agent)
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
