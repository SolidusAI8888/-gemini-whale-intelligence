from __future__ import annotations

from datetime import date, timedelta

from app.site_data import CORE_ASSETS, build_site_payload
from app.collectors.congress_holdings import parse_house_annual_holdings


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


def test_v50_impossible_future_transaction_date_is_not_charted():
    payload = build_site_payload([{
        "source_id": "house-option-expiry", "ticker": "MSFT", "source": "POLITICAL_HOUSE",
        "action": "BUY", "transaction_code": "P", "whale_name": "Example filer",
        "whale_category": "Political:House", "amount_usd": 750_000,
        "trade_date": "2026-10-16", "filing_date": "2026-09-14", "raw_json": {},
    }])
    assert payload["events"] == []


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


def test_v59_action_concentration_periods_recompute_event_population():
    ages = (10, 45, 100, 220, 500)
    rows = [{
        "source_id": f"period-{age}", "ticker": "UBER", "source": "POLITICAL_HOUSE",
        "action": "BUY", "transaction_code": "P", "whale_name": f"Filer {age}",
        "whale_category": "Political:House", "amount_usd": 100_000,
        "trade_date": (date.today() - timedelta(days=age)).isoformat(),
        "filing_date": (date.today() - timedelta(days=max(age - 2, 0))).isoformat(), "raw_json": {},
    } for age in ages]
    periods = build_site_payload(rows)["concentration_periods"]

    assert periods["all"][0]["increase_event_count"] == 5
    assert periods["1y"][0]["increase_event_count"] == 4
    assert periods["6m"][0]["increase_event_count"] == 3
    assert periods["3m"][0]["increase_event_count"] == 2
    assert periods["1m"][0]["increase_event_count"] == 1


def test_v59_alphabet_share_classes_share_one_action_rank():
    rows = [{
        "source_id": f"alphabet-{ticker}", "ticker": ticker, "source": "POLITICAL_HOUSE",
        "action": "BUY", "transaction_code": "P", "whale_name": f"Filer {ticker}",
        "whale_category": "Political:House", "amount_usd": 100_000,
        "trade_date": (date.today() - timedelta(days=10)).isoformat(),
        "filing_date": (date.today() - timedelta(days=8)).isoformat(), "raw_json": {},
    } for ticker in ("GOOG", "GOOGL")]
    concentration = build_site_payload(rows)["concentration"]

    assert len(concentration) == 1
    assert concentration[0]["ticker"] == "GOOG"
    assert concentration[0]["increase_event_count"] == 2


def test_v57_form4_post_transaction_shares_are_current_holdings_and_identity_is_canonical():
    rows = [{
        "source_id": "form4-uber-ceo", "ticker": "UBER", "source": "SEC_FORM4",
        "action": "SELL", "transaction_code": "S", "whale_name": "KHOSROWSHAHI DARA",
        "insider_role": "CEO", "amount_usd": 2_000_000, "shares": 20_000,
        "trade_date": "2026-08-03", "filing_date": "2026-08-05",
        "raw_json": {"security_title": "Common Stock", "shares_owned_following": "172507"},
    }]
    payload = build_site_payload(rows)
    assert payload["events"][0]["actor"] == "Dara Khosrowshahi"
    holding = payload["holdings"][0]
    assert holding["actor"] == "Dara Khosrowshahi"
    assert holding["shares"] == 172_507
    assert holding["amount_display"] == "172,507 shares"
    assert holding["holding_basis"] == "form4_post_transaction_shares"


def test_v57_form4_derivatives_do_not_become_current_holdings():
    rows = [{
        "source_id": "form4-option", "ticker": "MSFT", "source": "SEC_FORM4",
        "action": "BUY", "transaction_code": "A", "whale_name": "Example Officer",
        "trade_date": "2026-08-03", "filing_date": "2026-08-05",
        "raw_json": {"security_title": "Restricted Stock Unit", "shares_owned_following": "50000"},
    }]
    assert build_site_payload(rows)["holdings"] == []


def test_v57_house_annual_parser_keeps_stocks_and_excludes_options():
    text = """Filing Date: 05/15/2026
Alphabet Inc. - Class A (GOOGL) [ST] SP $5,000,001 -
$25,000,000
Alphabet Inc. - Class A Common Stock (GOOGL) [OP] SP $1,000,001 -
$5,000,000
"""
    rows = parse_house_annual_holdings(
        text, filer_name="Nancy Pelosi", role="Member", source_url="https://example.test/annual.pdf"
    )
    assert len(rows) == 1
    assert rows[0]["ticker"] == "GOOG"
    assert rows[0]["amount_usd"] == 15_000_000.5
    assert rows[0]["action"] == "HOLDING"
