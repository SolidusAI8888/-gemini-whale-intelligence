from app.domain.asset_quality import normalize_oge_asset
from app.domain.trade_classification import is_primary_transaction, primary_transactions
from app.reports.v40_oge import build_cabinet_oge_radar


def test_oge_normalizer_extracts_core_entity_from_table_windows():
    cases = {
        "RATE TERM 1 Bank of America, N.A Secured Facility Over $50,000,000": "Bank of America, N.A.",
        "N/A On Demand 3 Bank of America, N.A See Endnote Secured Facility Over $50,000,000": "Bank of America, N.A.",
        "14.6 Cantor Fitzgerald, L.P. See Endnote N/A Over $50,000,000": "Cantor Fitzgerald, L.P.",
        "2 HWL Personal Asset Trust No 2.1 BGC Group, Inc. (BGC) N/A Over $50,000,000": "BGC Group, Inc. (BGC)",
    }
    for raw, expected in cases.items():
        normalized = normalize_oge_asset(raw)
        assert normalized.quality == "accepted"
        assert normalized.name == expected


def test_oge_normalizer_rejects_terms_and_income_types():
    for raw in [
        "N/A On Demand",
        "N/A Interest",
        "N/A Rent or Royalties",
        "Government guaranteed collateral)",
        "RATE TERM",
        "N/A None (or less",
    ]:
        assert normalize_oge_asset(raw).quality == "rejected"


def test_oge_normalizer_classifies_legal_entities():
    assert normalize_oge_asset("Cantor Fitzgerald, L.P.").category == "私募/LLC/信托"
    assert normalize_oge_asset("BGC Group, Inc. (BGC)").category == "股票/上市证券"
    assert normalize_oge_asset("Bank of America, N.A.").category == "公司权益/商业权益"


def test_oge_radar_deduplicates_windows_by_normalized_entity():
    rows = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "filing_url": "https://example.com/278e.pdf",
            "amount_usd": 50_000_000,
            "raw_json": {"asset_name": "RATE TERM 1 Bank of America, N.A Secured Facility Over $50,000,000"},
        },
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "filing_url": "https://example.com/278e.pdf",
            "amount_usd": 50_000_000,
            "raw_json": {"asset_name": "N/A On Demand 3 Bank of America, N.A See Endnote Over $50,000,000"},
        },
    ]
    html = build_cabinet_oge_radar(rows)
    assert html.count("Bank of America, N.A.") == 1
    assert "RATE TERM" not in html
    assert "On Demand" not in html


def test_tiny_broker_affiliate_buy_and_sell_are_not_signals():
    rows = [
        {
            "source": "SEC Form 4",
            "action": "BUY",
            "transaction_code": "P",
            "amount_usd": 368,
            "whale_name": "MERRILL LYNCH, PIERCE, FENNER & SMITH INC.",
            "ticker": "NMZ",
        },
        {
            "source": "SEC Form 4",
            "action": "SELL",
            "transaction_code": "S",
            "amount_usd": 370,
            "whale_name": "BANK OF AMERICA CORP /DE/",
            "ticker": "NMZ",
        },
    ]
    assert not is_primary_transaction(rows[0])
    assert not is_primary_transaction(rows[1])
    assert primary_transactions(rows) == []


def test_legitimate_political_sell_remains_after_bad_buy_is_removed():
    bad_buy = {
        "source": "POLITICAL_HOUSE",
        "action": "BUY",
        "amount_usd": 2,
        "ticker": "HON",
    }
    legitimate_sell = {
        "source": "POLITICAL_HOUSE",
        "action": "SELL",
        "amount_usd": 32_500,
        "ticker": "HON",
    }
    assert not is_primary_transaction(bad_buy)
    assert is_primary_transaction(legitimate_sell)
