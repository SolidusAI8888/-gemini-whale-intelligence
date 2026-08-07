import json

from app.collectors.oge_executive_v42 import normalize_oge_asset_row_for_tests


def _row(asset_name: str) -> dict:
    return {
        "source_id": "x",
        "ticker": "OGE-ASSET",
        "company_name": asset_name,
        "filing_url": "https://example.test/oge.pdf",
        "whale_name": "Official",
        "whale_category": "Executive:Cabinet",
        "insider_role": "Secretary",
        "action": "HOLDING",
        "transaction_code": "H",
        "amount_usd": 50_000_000,
        "trade_date": "2026-01-01",
        "filing_date": "2026-01-01",
        "source": "OGE_EXECUTIVE_ASSET",
        "raw_json": json.dumps({"asset_name": asset_name, "amount_range_label": ">$50,000,000"}),
    }


def test_v42_drops_semantic_non_assets_before_db_upsert():
    for text in [
        "Over $50,000,000",
        "Dividends $100,001",
        "Crop Sales $51,180",
        "Interest $25,000",
        "RATE TERM 1",
    ]:
        assert normalize_oge_asset_row_for_tests(_row(text)) is None


def test_v42_normalizes_asset_before_db_upsert():
    normalized = normalize_oge_asset_row_for_tests(
        _row("RATE TERM 1 Bank of America, N.A Secured Facility Over $50,000,000")
    )

    assert normalized is not None
    assert normalized["company_name"] == "Bank of America, N.A."
    raw = json.loads(normalized["raw_json"])
    assert raw["asset_name"] == "Bank of America, N.A."
    assert raw["canonical_asset_key"] == "bank of america n a"
    assert raw["asset_category"] == "公司权益/商业权益"
    assert raw["v42_quality_gate"] == "accepted"
