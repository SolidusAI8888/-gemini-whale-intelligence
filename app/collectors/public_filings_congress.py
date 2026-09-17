from __future__ import annotations

"""Import normalized House and Senate PTR rows with original filing links."""

from datetime import date, timedelta
import json
from typing import Any

import requests

BASE_URL = "https://publicfilings.org/congress/data/feed/{part}.v1.json"
TXN_COLUMNS = ("filed", "traded", "name", "bioguide", "party", "state", "district", "chamber", "ticker", "side", "owner", "low", "high", "lag", "late", "flags", "doc", "asset", "assetType", "txnId")
ACTION_MAP = {"purchase": "BUY", "sale": "SELL", "sale_partial": "SELL", "sale_full": "SELL"}


def _parts_for_cutoff(cutoff: date, today: date) -> list[str]:
    return [f"{year}-{number}" for year in range(today.year, cutoff.year - 1, -1) for number in range(1, 4)]


def _amount_midpoint(low: Any, high: Any) -> float | None:
    try:
        lower, upper = float(low), float(high)
    except (TypeError, ValueError):
        return None
    return (lower + upper) / 2 if lower >= 0 and upper >= lower else None


def collect_public_filings_congress_trades(lookback_days: int = 620, user_agent: str = "WhaleIntelligence contact@example.com", target_tickers: set[str] | None = None) -> list[dict[str, Any]]:
    """Use Public Filings as a normalizer; retain official House/Senate evidence URLs."""
    today = date.today()
    cutoff = today - timedelta(days=max(1, int(lookback_days)))
    tickers = {ticker.upper() for ticker in (target_tickers or set())}
    output: dict[str, dict[str, Any]] = {}
    session = requests.Session()
    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    for part in _parts_for_cutoff(cutoff, today):
        response = session.get(BASE_URL.format(part=part), headers=headers, timeout=30)
        if response.status_code == 404:
            continue
        response.raise_for_status()
        payload = response.json()
        columns = tuple(payload.get("txn_cols") or TXN_COLUMNS)
        for raw_row in payload.get("rows") or []:
            if not raw_row or raw_row[0] != "t":
                continue
            row = dict(zip(columns, raw_row[1:]))
            traded = str(row.get("traded") or "")[:10]
            ticker = str(row.get("ticker") or "").strip().upper()
            document = str(row.get("doc") or "").strip()
            action = ACTION_MAP.get(str(row.get("side") or "").strip().lower())
            if not action or not traded or traded < cutoff.isoformat() or not ticker or not document or (tickers and ticker not in tickers):
                continue
            chamber = str(row.get("chamber") or "").strip().upper()
            source_id = f"PUBLIC_FILINGS:{row.get('txnId') or part + ':' + str(len(output))}"
            output[source_id] = {
                "source_id": source_id, "ticker": ticker,
                "company_name": str(row.get("asset") or ticker).splitlines()[0],
                "cik": None, "accession_number": str(row.get("txnId") or ""),
                "filing_url": document, "whale_name": " ".join(str(row.get("name") or "").split()),
                "whale_category": f"Political {chamber.title()}",
                "insider_role": f"{chamber.title()} member · {row.get('party') or ''}-{row.get('state') or ''}",
                "action": action, "transaction_code": str(row.get("side") or ""),
                "amount_usd": _amount_midpoint(row.get("low"), row.get("high")),
                "shares": None, "price": None, "trade_date": traded,
                "filing_date": str(row.get("filed") or "")[:10] or None,
                "source": f"POLITICAL_{chamber}",
                "raw_json": json.dumps({**row, "normalization_provider": "Public Filings", "dataset_build": payload.get("build_id")}, ensure_ascii=False),
            }
    return list(output.values())
