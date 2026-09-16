from __future__ import annotations

from app.site_data import CORE_ASSETS, build_site_payload


def test_v48_core_universe_is_exact_and_stable():
    assert len(CORE_ASSETS) == 21
    assert {"BTC", "SPCX", "PURR", "UBER", "MSFT", "INTC"} <= set(CORE_ASSETS)


def test_v48_payload_contains_actions_only_and_separates_institution_people():
    rows = [
        {
            "source_id": "13f-uber", "ticker": "UBER", "source": "INSTITUTIONAL_13F",
            "action": "HOLDING_13F", "whale_name": "Bill Ackman",
            "insider_role": "Pershing Square Capital Management", "amount_usd": 2_150_000_000,
            "shares": 30_000_000, "trade_date": "2026-03-31", "filing_date": "2026-05-15",
            "raw_json": {"manager": "Pershing Square Capital Management", "lead_investor": "Bill Ackman"},
        },
        {
            "source_id": "house-intc", "ticker": "INTC", "source": "POLITICAL_HOUSE",
            "action": "BUY", "transaction_code": "P", "whale_name": "Nancy Pelosi",
            "whale_category": "Political:House", "amount_usd": 3_000_000,
            "trade_date": "2026-05-29", "filing_date": "2026-06-23", "raw_json": {},
        },
        {
            "source_id": "noise", "ticker": "MSFT", "source": "MEDIA",
            "action": "OPINION", "whale_name": "Commentator", "trade_date": "2026-06-01",
            "filing_date": "2026-06-01", "raw_json": {},
        },
    ]
    payload = build_site_payload(rows)
    assert payload["principles"]["opinions_included"] is False
    assert all(event["action"] != "OPINION" for event in payload["events"])
    institutional = next(event for event in payload["events"] if event["source"] == "SEC 13F")
    assert institutional["actor"] == "Pershing Square Capital Management"
    assert institutional["responsible_people"] == ["Bill Ackman"]
    assert institutional["attribution"] == "institution_not_person"


def test_v48_public_date_and_lag_are_first_class_fields():
    payload = build_site_payload([{
        "source_id": "house-uber", "ticker": "UBER", "source": "POLITICAL_HOUSE",
        "action": "BUY", "transaction_code": "P", "whale_name": "Example filer",
        "whale_category": "Political:House", "amount_usd": 750_000,
        "trade_date": "2026-05-29", "filing_date": "2026-06-23", "raw_json": {},
    }])
    event = payload["events"][0]
    assert event["occurred_at"] == "2026-05-29"
    assert event["published_at"] == "2026-06-23"
    assert event["lag_days"] == 25
