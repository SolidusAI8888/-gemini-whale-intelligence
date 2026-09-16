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
    institutional = next(event for event in payload["holdings"] if event["source"] == "SEC 13F")
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


def test_v49_holding_snapshots_are_not_chart_pins_and_have_their_own_concentration():
    rows = [{
        "source_id": "13f-msft-q1", "ticker": "MSFT", "source": "INSTITUTIONAL_13F",
        "action": "HOLDING_13F", "whale_name": "Named investor",
        "insider_role": "Example Capital", "amount_usd": 500_000_000,
        "shares": 1_000_000, "trade_date": "2026-03-31", "filing_date": "2026-05-15",
        "raw_json": {"manager": "Example Capital", "cio": "Named investor"},
    }]
    payload = build_site_payload(rows)
    assert payload["events"] == []
    assert payload["holdings"][0]["actor"] == "Example Capital"
    assert payload["holding_concentration"][0]["ticker"] == "MSFT"
    assert payload["holding_concentration"][0]["holder_count"] == 1


def test_v49_real_price_history_and_market_snapshot_are_exported_without_synthesis():
    payload = build_site_payload(
        [],
        [{"ticker": "UBER", "price": 91.25, "change_pct": 1.5}],
        [
            {"ticker": "UBER", "price_date": "2026-09-14", "close": 90},
            {"ticker": "UBER", "price_date": "2026-09-15", "close": 91.25},
        ],
    )
    uber = next(asset for asset in payload["core_assets"] if asset["ticker"] == "UBER")
    assert uber["market"]["price"] == 91.25
    assert uber["price_history"] == [
        {"date": "2026-09-14", "close": 90.0},
        {"date": "2026-09-15", "close": 91.25},
    ]
    assert payload["metrics"]["history_asset_count"] == 1


def test_v49_action_concentration_counts_independent_actors_and_sources():
    rows = [
        {"source_id": "house-uber", "ticker": "UBER", "source": "POLITICAL_HOUSE", "action": "BUY", "transaction_code": "P", "whale_name": "House filer", "whale_category": "Political:House", "amount_usd": 750_000, "trade_date": "2026-05-29", "filing_date": "2026-06-23", "raw_json": {}},
        {"source_id": "sec-uber", "ticker": "UBER", "source": "SEC_FORM4", "action": "BUY", "transaction_code": "P", "whale_name": "Company officer", "whale_category": "Business", "amount_usd": 250_000, "trade_date": "2026-06-02", "filing_date": "2026-06-04", "raw_json": {}},
    ]
    payload = build_site_payload(rows)
    row = payload["concentration"][0]
    assert row["ticker"] == "UBER"
    assert row["actor_count"] == 2
    assert row["group_count"] == 2
    assert row["net_amount_usd"] == 1_000_000
