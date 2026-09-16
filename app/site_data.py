from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.db import get_conn, init_db
from app.domain.trade_classification import is_primary_transaction


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
    return {
        "id": str(row.get("source_id") or ""),
        "ticker": str(row.get("ticker") or "").upper(),
        "action": str(row.get("action") or "").upper(),
        "actor": actor,
        "organization": organization,
        "role": str(row.get("insider_role") or row.get("whale_category") or "").strip(),
        "responsible_people": responsible_people,
        "ownership": owner or None,
        "attribution": attribution,
        "amount_usd": float(row.get("amount_usd") or 0),
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
    return _event_from_row(row)


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
                base["change_basis"] = "quarterly_snapshot_comparison"
            base["id"] = f"{base['id']}:derived"
            events.append(base)
    return events


def build_site_payload(rows: Iterable[Mapping[str, Any]], snapshots: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
    records = [dict(row) for row in rows]
    primary = [event for row in records if (event := _transaction_event(row))]
    holdings = _holding_changes(records)
    market = {str(row.get("ticker") or "").upper(): dict(row) for row in snapshots}
    events = [event for event in primary + holdings if event["ticker"]]
    events.sort(key=lambda event: (event.get("published_at") or "", event.get("occurred_at") or ""), reverse=True)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "principles": {"actions_only": True, "opinions_included": False, "institution_person_separation": True},
        "core_assets": [{"ticker": ticker, "market": market.get(ticker)} for ticker in CORE_ASSETS],
        "events": events,
    }


def export_site_payload(destination: Path = Path("site/public/data/site-data.json")) -> Path:
    init_db()
    with get_conn() as conn:
        rows = [_dict(row) for row in conn.execute("SELECT * FROM trades ORDER BY filing_date DESC, trade_date DESC")]
        snapshots = [_dict(row) for row in conn.execute("SELECT * FROM market_snapshots")]
    payload = build_site_payload(rows, snapshots)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


if __name__ == "__main__":
    print(export_site_payload())
