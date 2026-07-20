from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Mapping, Any

from app.intelligence.models import Signal, SignalDirection, SignalSource


def _source(row: Mapping[str, Any]) -> SignalSource | None:
    source = str(row.get("source") or "").upper()
    category = str(row.get("whale_category") or "").upper()
    if "13F" in source or "13F" in category:
        return SignalSource.INSTITUTIONAL_13F
    if source.startswith("POLITICAL") or "CONGRESS" in source or "POLITICAL" in category:
        return SignalSource.CONGRESS
    if source.startswith("OGE") or "EXECUTIVE:CABINET" in category:
        return SignalSource.OGE
    if source.startswith("SEC_FORM4") or "INSIDER" in category or source == "SEC":
        return SignalSource.FORM4
    return None


def _direction(action: str) -> SignalDirection:
    action = (action or "").upper()
    if action in {"BUY", "PURCHASE", "P", "INCREASE", "NEW", "NEW_POSITION", "ADD"}:
        return SignalDirection.BULLISH
    if action in {"SELL", "SALE", "S", "DECREASE", "LIQUIDATED", "EXIT", "REDUCE"}:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def normalize_trade(row: Mapping[str, Any]) -> Signal | None:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker or ticker in {"UNKNOWN", "N/A"} or ticker.startswith("CUSIP:"):
        return None
    source = _source(row)
    if source is None:
        return None
    action = str(row.get("action") or "").upper()
    direction = _direction(action)
    if direction is SignalDirection.NEUTRAL:
        return None
    event_date = str(row.get("trade_date") or row.get("filing_date") or "")[:10]
    amount = max(0.0, float(row.get("amount_usd") or 0.0))
    confidence = 0.75 if source in {SignalSource.FORM4, SignalSource.INSTITUTIONAL_13F} else 0.65
    return Signal(
        ticker=ticker,
        source=source,
        direction=direction,
        actor=str(row.get("whale_name") or "Unknown"),
        actor_category=str(row.get("whale_category") or "Unknown"),
        event_date=event_date,
        amount_usd=amount,
        action=action,
        confidence=confidence,
        source_id=str(row.get("source_id") or ""),
        metadata={
            "company_name": row.get("company_name"),
            "insider_role": row.get("insider_role"),
            "filing_url": row.get("filing_url"),
            "shares": row.get("shares"),
            "price": row.get("price"),
        },
    )


def normalize_trades(rows: Iterable[Mapping[str, Any]]) -> list[Signal]:
    out: list[Signal] = []
    seen: set[str] = set()
    for row in rows:
        signal = normalize_trade(row)
        if signal is None:
            continue
        identity = signal.source_id or "|".join((signal.ticker, signal.source.value, signal.actor, signal.event_date, signal.action, str(signal.amount_usd)))
        if identity in seen:
            continue
        seen.add(identity)
        out.append(signal)
    return out
