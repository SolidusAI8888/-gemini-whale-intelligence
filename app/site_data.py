from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
import json
import math
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from app.db import get_conn, init_db
from app.collectors.sec_13f import CUSIP_TICKER_HINTS, ISSUER_TICKER_HINTS
from app.domain.trade_classification import is_asset_or_holding_disclosure, is_primary_transaction


CORE_ASSETS = (
    "BTC", "MSTR", "NVDA", "TSLA", "SPCX", "GOOG", "PLTR", "ORCL", "HOOD",
    "INTC", "MU", "AAPL", "AMZN", "AMD", "GLW", "MRVL", "MSFT", "UBER",
    "AVGO", "RKLB", "PURR",
)


def _dict(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()} if hasattr(row, "keys") else dict(row)


def _raw(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _days_between(occurred: str, published: str) -> int | None:
    try:
        start = date.fromisoformat(str(occurred)[:10])
        end = date.fromisoformat(str(published)[:10])
        return max(0, (end - start).days)
    except (TypeError, ValueError):
        return None


def _source_semantics(row: Mapping[str, Any]) -> tuple[str, str]:
    source = str(row.get("source") or "").upper()
    if source == "INSTITUTIONAL_13F":
        return "SEC 13F", "B"
    if source.startswith("POLITICAL"):
        return "Congress PTR", "A"
    if source.startswith("OGE"):
        return "OGE", "A"
    if source.startswith("SEC"):
        return "SEC Form 4", "A"
    return source or "Public filing", "B"


def _institution_identity(row: Mapping[str, Any]) -> tuple[str, str, list[str]]:
    raw = _raw(row)
    manager = str(raw.get("manager") or row.get("insider_role") or row.get("whale_name") or "Unknown institution").strip()
    people = []
    for key in ("lead_investor", "chairman", "ceo", "cfo", "cio", "portfolio_manager"):
        value = str(raw.get(key) or "").strip()
        if value and value != manager and value not in people:
            people.append(value)
    return manager, manager, people


def _event_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    source_label, grade = _source_semantics(row)
    occurred = str(row.get("trade_date") or row.get("filing_date") or "")[:10]
    published = str(row.get("filing_date") or row.get("trade_date") or "")[:10]
    source = str(row.get("source") or "").upper()
    raw = _raw(row)
    actor = str(row.get("whale_name") or "Unknown filer").strip()
    organization = str(row.get("insider_role") or row.get("whale_category") or "").strip()
    responsible_people: list[str] = []
    attribution = "reported_person_or_household"
    if source == "INSTITUTIONAL_13F":
        actor, organization, responsible_people = _institution_identity(row)
        attribution = "institution_not_person"
    owner = str(raw.get("owner") or raw.get("ownership") or raw.get("owner_type") or "").strip()
    raw_text = " ".join(str(value or "") for value in raw.values())
    amount_match = re.search(
        r"\$\s*[\d,]+(?:\.\d+)?\s*(?:-|–|—|to)\s*\$?\s*[\d,]+(?:\.\d+)?",
        raw_text,
        re.IGNORECASE,
    )
    ticker = str(row.get("ticker") or "").upper()
    if ticker.startswith("CUSIP:"):
        cusip = ticker.split(":", 1)[1]
        issuer = str(row.get("company_name") or raw.get("nameOfIssuer") or "").upper()
        ticker = CUSIP_TICKER_HINTS.get(cusip, "")
        if not ticker:
            ticker = next((symbol for name, symbol in ISSUER_TICKER_HINTS.items() if name in issuer), "")
        # Never expose an opaque identifier as if it were a tradable symbol.
        # Unmapped rows remain identifiable by issuer name and can be repaired
        # in the mapping table without leaking CUSIP syntax into the product.
        if not ticker:
            ticker = re.sub(r"[^A-Z0-9 .&-]", "", issuer).strip() or "UNMAPPED SECURITY"
    return {
        "id": str(row.get("source_id") or ""),
        "ticker": ticker,
        "action": str(row.get("action") or "").upper(),
        "actor": actor,
        "organization": organization,
        "role": str(row.get("insider_role") or row.get("whale_category") or "").strip(),
        "responsible_people": responsible_people,
        "ownership": owner or None,
        "attribution": attribution,
        "amount_usd": float(row.get("amount_usd") or 0),
        "amount_display": amount_match.group(0).replace(" ", "") if amount_match else None,
        "shares": float(row.get("shares") or 0),
        "price": float(row.get("price") or 0),
        "occurred_at": occurred,
        "published_at": published,
        "lag_days": _days_between(occurred, published),
        "source": source_label,
        "source_url": str(row.get("filing_url") or ""),
        "evidence_grade": grade,
    }


def _transaction_event(row: Mapping[str, Any]) -> dict[str, Any] | None:
    if not is_primary_transaction(row):
        return None
    event = _event_from_row(row)
    # Option-expiry dates occasionally appear in congressional disclosure text
    # and must never be mistaken for transaction dates. A trade cannot occur
    # after the filing was already public, so fail closed on that impossible
    # chronology instead of pinning a future event to the price chart.
    occurred = event.get("occurred_at") or ""
    published = event.get("published_at") or ""
    if occurred and published and occurred > published:
        return None
    return event


def _holding_changes(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if str(row.get("source") or "").upper() != "INSTITUTIONAL_13F":
            continue
        manager, _, _ = _institution_identity(row)
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            groups[(manager, ticker)].append(row)
    events: list[dict[str, Any]] = []
    for records in groups.values():
        records.sort(key=lambda item: str(item.get("trade_date") or item.get("filing_date") or ""))
        for index, current in enumerate(records):
            base = _event_from_row(current)
            current_shares = float(current.get("shares") or 0)
            current_value = float(current.get("amount_usd") or 0)
            if index == 0:
                base["action"] = "HOLDING"
                base["change_basis"] = "first_observed_snapshot"
            else:
                previous = records[index - 1]
                previous_shares = float(previous.get("shares") or 0)
                previous_value = float(previous.get("amount_usd") or 0)
                current_measure = current_shares or current_value
                previous_measure = previous_shares or previous_value
                if current_measure > previous_measure:
                    base["action"] = "ADD"
                elif current_measure < previous_measure:
                    base["action"] = "REDUCE"
                else:
                    base["action"] = "HOLDING"
                if base["action"] != "HOLDING":
                    base["amount_usd"] = abs(current_value - previous_value)
                    base["amount_display"] = None
                    base["shares"] = abs(current_shares - previous_shares)
                base["change_basis"] = "quarterly_snapshot_comparison"
            base["id"] = f"{base['id']}:derived"
            events.append(base)
    return events


def _current_holdings(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return the latest observed holding per filer/institution and ticker."""
    latest: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for row in rows:
        if not is_asset_or_holding_disclosure(row):
            continue
        event = _event_from_row(row)
        ticker = event["ticker"]
        if not ticker:
            continue
        key = (event["actor"], ticker)
        observed = event["published_at"] or event["occurred_at"]
        if key not in latest or observed >= latest[key][0]:
            latest[key] = (observed, event)
    holdings = [event for _, event in latest.values()]
    holdings.sort(key=lambda event: (event["ticker"], -event["amount_usd"], event["actor"]))
    return holdings


def _concentration(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("action") in {"BUY", "SELL", "NEW", "ADD", "REDUCE", "EXIT"}:
            groups[str(event.get("ticker") or "")].append(event)
    aggregates = []
    positive = {"BUY", "NEW", "ADD"}
    negative = {"SELL", "REDUCE", "EXIT"}
    for ticker, items in groups.items():
        def side_metrics(actions: set[str]) -> dict[str, Any]:
            side = [item for item in items if item.get("action") in actions]
            return {
                "amount": sum(float(item.get("amount_usd") or 0) for item in side),
                "actors": len({str(item.get("actor") or "") for item in side}),
                "events": len(side),
                "sources": sorted({str(item.get("source") or "") for item in side}),
                "quality": sum(1.0 if item.get("evidence_grade") == "A" else 0.75 for item in side) / max(1, len(side)),
            }
        up = side_metrics(positive)
        down = side_metrics(negative)
        aggregates.append({
            "ticker": ticker,
            "actor_count": len({str(item.get("actor") or "") for item in items}),
            "group_count": len({str(item.get("source") or "") for item in items}),
            "source_names": sorted({str(item.get("source") or "") for item in items}),
            "event_count": len(items),
            "buy_amount_usd": up["amount"],
            "sell_amount_usd": down["amount"],
            "net_amount_usd": up["amount"] - down["amount"],
            "increase_actor_count": up["actors"],
            "decrease_actor_count": down["actors"],
            "increase_event_count": up["events"],
            "decrease_event_count": down["events"],
            "increase_source_names": up["sources"],
            "decrease_source_names": down["sources"],
            "increase_quality": up["quality"],
            "decrease_quality": down["quality"],
        })
    def maximum(field: str) -> float:
        return max((float(item[field]) for item in aggregates), default=1.0) or 1.0
    max_actor = max(maximum("increase_actor_count"), maximum("decrease_actor_count"))
    max_events = max(maximum("increase_event_count"), maximum("decrease_event_count"))
    max_amount = max(maximum("buy_amount_usd"), maximum("sell_amount_usd"))
    max_sources = max(
        max((len(item["increase_source_names"]) for item in aggregates), default=1),
        max((len(item["decrease_source_names"]) for item in aggregates), default=1),
    )
    for item in aggregates:
        for prefix, amount_field in (("increase", "buy_amount_usd"), ("decrease", "sell_amount_usd")):
            if not item[f"{prefix}_event_count"]:
                item[f"{prefix}_score"] = 0
                continue
            actor_component = item[f"{prefix}_actor_count"] / max_actor
            source_component = len(item[f"{prefix}_source_names"]) / max_sources
            amount_component = math.log1p(item[amount_field]) / math.log1p(max_amount)
            event_component = math.log1p(item[f"{prefix}_event_count"]) / math.log1p(max_events)
            item[f"{prefix}_score"] = round(35 * actor_component + 20 * source_component + 20 * amount_component + 15 * item[f"{prefix}_quality"] + 10 * event_component)
        item["score"] = max(item["increase_score"], item["decrease_score"])
        item.pop("increase_quality", None)
        item.pop("decrease_quality", None)
    return sorted(aggregates, key=lambda item: (item["score"], item["event_count"], abs(item["net_amount_usd"])), reverse=True)


def _holding_concentration(holdings: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for holding in holdings:
        groups[str(holding.get("ticker") or "")].append(holding)
    output = [{
        "ticker": ticker,
        "holder_count": len({str(item.get("actor") or "") for item in items}),
        "source_count": len({str(item.get("source") or "") for item in items}),
        "source_names": sorted({str(item.get("source") or "") for item in items}),
        "position_count": len(items),
        "reported_value_usd": sum(float(item.get("amount_usd") or 0) for item in items),
    } for ticker, items in groups.items()]
    max_holders = max((item["holder_count"] for item in output), default=1)
    max_sources = max((item["source_count"] for item in output), default=1)
    max_positions = max((item["position_count"] for item in output), default=1)
    max_value = max((item["reported_value_usd"] for item in output), default=1)
    for item in output:
        item["score"] = round(
            45 * item["holder_count"] / max_holders
            + 15 * item["source_count"] / max_sources
            + 15 * math.log1p(item["position_count"]) / math.log1p(max_positions)
            + 25 * math.log1p(item["reported_value_usd"]) / math.log1p(max_value)
        )
    return sorted(output, key=lambda item: (item["score"], item["holder_count"], item["reported_value_usd"]), reverse=True)


def build_site_payload(
    rows: Iterable[Mapping[str, Any]],
    snapshots: Iterable[Mapping[str, Any]] = (),
    price_history: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    records = [dict(row) for row in rows]
    primary = [event for row in records if (event := _transaction_event(row))]
    holding_changes = _holding_changes(records)
    current_holdings = _current_holdings(records)
    market = {str(row.get("ticker") or "").upper(): dict(row) for row in snapshots}
    histories: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in price_history:
        ticker = str(point.get("ticker") or "").upper()
        try:
            close = float(point.get("close") or 0)
            open_price = float(point.get("open") or close)
            high = float(point.get("high") or max(open_price, close))
            low = float(point.get("low") or min(open_price, close))
            volume = float(point.get("volume") or 0)
        except (TypeError, ValueError):
            close = 0
        day = str(point.get("price_date") or point.get("date") or "")[:10]
        if ticker and day and close > 0:
            history_point = {"date": day, "close": close}
            if any(point.get(key) is not None for key in ("open", "high", "low")):
                history_point.update({"open": open_price, "high": high, "low": low, "volume": volume})
            histories[ticker].append(history_point)
    for points in histories.values():
        points.sort(key=lambda point: point["date"])
    # Holdings are not transactions. Only a change inferred from two 13F
    # snapshots is eligible for a chart pin.
    events = [event for event in primary + holding_changes if event["ticker"] and event["action"] != "HOLDING"]
    events.sort(key=lambda event: (event.get("published_at") or "", event.get("occurred_at") or ""), reverse=True)
    return {
        "schema_version": 3,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "mode": "production" if events or current_holdings or market else "empty",
        "principles": {"actions_only": True, "opinions_included": False, "institution_person_separation": True},
        "core_assets": [
            {"ticker": ticker, "market": market.get(ticker), "price_history": histories.get(ticker, [])}
            for ticker in CORE_ASSETS
        ],
        "events": events,
        "holdings": current_holdings,
        "concentration": _concentration(events),
        "holding_concentration": _holding_concentration(current_holdings),
        "metrics": {
            "event_count": len(events),
            "holding_count": len(current_holdings),
            "priced_asset_count": sum(1 for ticker in CORE_ASSETS if market.get(ticker)),
            "history_asset_count": sum(1 for ticker in CORE_ASSETS if histories.get(ticker)),
        },
    }


def export_site_payload(destination: Path = Path("site/public/data/site-data.json")) -> Path:
    init_db()
    with get_conn() as conn:
        rows = [_dict(row) for row in conn.execute("SELECT * FROM trades ORDER BY filing_date DESC, trade_date DESC")]
        snapshots = [_dict(row) for row in conn.execute("SELECT * FROM market_snapshots")]
        history = [_dict(row) for row in conn.execute(
            "SELECT * FROM market_price_history ORDER BY ticker, price_date"
        )]
    payload = build_site_payload(rows, snapshots, history)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(export_site_payload())
