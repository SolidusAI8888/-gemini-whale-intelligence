from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Iterable, Mapping

from app.intelligence.models import Signal, SignalDirection, SignalSource

# Verified seed map. Mapping is performed before grouping/scoring so the same
# security cannot appear once as a ticker and again as a CUSIP pseudo-ticker.
CUSIP_TO_TICKER = {
    "007903107": "AMD",
    "25809K105": "DASH",
    "N07059210": "ASML",
    "512807306": "LRCX",
    "512807108": "LRCX",  # legacy/alternate value observed in old caches
}

UNKNOWN_TICKERS = {"", "UNKNOWN", "N/A", "NONE", "NULL", "-"}


def canonical_ticker(ticker: Any = "", cusip: Any = "") -> str:
    raw = str(ticker or "").strip().upper()
    raw_cusip = str(cusip or "").strip().upper().replace(" ", "")
    if raw.startswith("CUSIP:"):
        raw_cusip = raw.split(":", 1)[1].strip().replace(" ", "")
        raw = ""
    mapped = CUSIP_TO_TICKER.get(raw_cusip)
    if mapped:
        return mapped
    if raw not in UNKNOWN_TICKERS:
        return raw
    # Unknown CUSIPs are intentionally excluded from WIS rather than treated as
    # independent tickers. They remain visible in the audit/detail report.
    return ""


def _raw_json(row: Mapping[str, Any]) -> dict[str, Any]:
    raw = row.get("raw_json")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
    return {}


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
    if action in {"BUY", "PURCHASE", "P", "INCREASE", "NEW", "NEW_POSITION", "ADD", "13F_INCREASE", "13F_NEW"}:
        return SignalDirection.BULLISH
    if action in {"SELL", "SALE", "S", "DECREASE", "LIQUIDATED", "EXIT", "REDUCE", "13F_DECREASE", "13F_EXIT"}:
        return SignalDirection.BEARISH
    return SignalDirection.NEUTRAL


def _normalize_ticker(row: Mapping[str, Any]) -> str:
    obj = _raw_json(row)
    return canonical_ticker(row.get("ticker"), row.get("cusip") or obj.get("cusip"))


def normalize_trade(row: Mapping[str, Any]) -> Signal | None:
    ticker = _normalize_ticker(row)
    if not ticker:
        return None
    source = _source(row)
    if source is None:
        return None
    action = str(row.get("action") or "").upper()
    direction = _direction(action)
    if direction is SignalDirection.NEUTRAL:
        return None
    event_date = str(row.get("trade_date") or row.get("filing_date") or "")[:10]
    try:
        amount = max(0.0, float(row.get("amount_usd") or 0.0))
    except (TypeError, ValueError):
        amount = 0.0
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
            "cusip": row.get("cusip") or _raw_json(row).get("cusip"),
        },
    )


def _institutional_delta_signals(rows: list[Mapping[str, Any]]) -> list[Signal]:
    """Convert quarterly 13F holdings into directional latest-vs-prior signals.

    HOLDING_13F is a stock snapshot, not a transaction. WIS therefore compares
    each manager's two newest report periods and emits one synthetic increase,
    decrease, new-position, or exit signal per security.
    """
    grouped: dict[str, dict[str, dict[str, Mapping[str, Any]]]] = defaultdict(lambda: defaultdict(dict))
    for row in rows:
        if _source(row) is not SignalSource.INSTITUTIONAL_13F:
            continue
        ticker = _normalize_ticker(row)
        if not ticker:
            continue
        obj = _raw_json(row)
        manager = str(obj.get("manager") or row.get("insider_role") or row.get("whale_name") or "Unknown").strip()
        period = str(obj.get("report_period") or row.get("trade_date") or "")[:10]
        if not period:
            continue
        existing = grouped[manager][period].get(ticker)
        if existing is None or float(row.get("amount_usd") or 0) > float(existing.get("amount_usd") or 0):
            grouped[manager][period][ticker] = row

    signals: list[Signal] = []
    for manager, periods in grouped.items():
        ordered = sorted(periods, reverse=True)
        if len(ordered) < 2:
            continue
        latest_period, prior_period = ordered[0], ordered[1]
        latest, prior = periods[latest_period], periods[prior_period]
        for ticker in set(latest) | set(prior):
            latest_row, prior_row = latest.get(ticker), prior.get(ticker)
            latest_amount = max(0.0, float((latest_row or {}).get("amount_usd") or 0.0))
            prior_amount = max(0.0, float((prior_row or {}).get("amount_usd") or 0.0))
            delta = latest_amount - prior_amount
            # Ignore tiny changes and ordinary HOLD snapshots.
            if abs(delta) < 1_000:
                continue
            if prior_amount <= 0 < latest_amount:
                action, direction = "13F_NEW", SignalDirection.BULLISH
            elif latest_amount <= 0 < prior_amount:
                action, direction = "13F_EXIT", SignalDirection.BEARISH
            elif delta > 0:
                action, direction = "13F_INCREASE", SignalDirection.BULLISH
            else:
                action, direction = "13F_DECREASE", SignalDirection.BEARISH
            source_row = latest_row or prior_row or {}
            lead = str(source_row.get("whale_name") or manager or "Unknown")
            source_id = f"13F_DELTA:{manager}:{prior_period}:{latest_period}:{ticker}"
            signals.append(Signal(
                ticker=ticker,
                source=SignalSource.INSTITUTIONAL_13F,
                direction=direction,
                actor=lead,
                actor_category="Institutional 13F",
                event_date=latest_period,
                amount_usd=abs(delta),
                action=action,
                confidence=0.75,
                source_id=source_id,
                metadata={
                    "manager": manager,
                    "prior_period": prior_period,
                    "latest_period": latest_period,
                    "prior_amount_usd": prior_amount,
                    "latest_amount_usd": latest_amount,
                    "delta_usd": delta,
                },
            ))
    return signals


def normalize_trades(rows: Iterable[Mapping[str, Any]]) -> list[Signal]:
    materialized = list(rows)
    out: list[Signal] = []
    seen: set[str] = set()

    # Real transaction-like sources.
    for row in materialized:
        if _source(row) is SignalSource.INSTITUTIONAL_13F and str(row.get("action") or "").upper() == "HOLDING_13F":
            continue
        signal = normalize_trade(row)
        if signal is None:
            continue
        identity = signal.source_id or "|".join((signal.ticker, signal.source.value, signal.actor, signal.event_date, signal.action, str(signal.amount_usd)))
        if identity not in seen:
            seen.add(identity)
            out.append(signal)

    # Directional 13F signals derived from two adjacent quarters.
    for signal in _institutional_delta_signals(materialized):
        if signal.source_id not in seen:
            seen.add(signal.source_id)
            out.append(signal)
    return out
