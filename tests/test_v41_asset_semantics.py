from app.domain.asset_semantics import parse_oge_asset_semantics


def test_semantic_parser_rejects_amount_only_rows():
    parsed = parse_oge_asset_semantics("Over $50,000,000")
    assert parsed.quality == "rejected"
    assert parsed.rejected_reason == "amount_only"
    assert parsed.asset_name == ""


def test_semantic_parser_rejects_income_type_rows():
    for text in ["Dividends $100,001", "Crop Sales $51,180", "Interest $25,000"]:
        parsed = parse_oge_asset_semantics(text)
        assert parsed.quality == "rejected"
        assert parsed.rejected_reason == "income_type"
        assert parsed.asset_name == ""


def test_semantic_parser_rejects_actual_na_prefixed_table_header_from_preview_cache():
    parsed = parse_oge_asset_semantics(
        "N/A # EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE"
    )
    assert parsed.quality == "rejected"
    assert parsed.rejected_reason == "table_header"
    assert parsed.asset_name == ""


def test_semantic_parser_rejects_numbered_table_header_after_empty_cell_marker():
    parsed = parse_oge_asset_semantics(
        "N/A 12 EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE"
    )
    assert parsed.quality == "rejected"
    assert parsed.rejected_reason == "table_header"


def test_semantic_parser_keeps_real_entities_and_strips_financing_terms():
    parsed = parse_oge_asset_semantics("Bank of America, N.A. Secured Facility")
    assert parsed.quality == "accepted"
    assert parsed.asset_name == "Bank of America, N.A."
    assert parsed.category == "公司权益/商业权益"


def test_semantic_parser_keeps_share_class_identity():
    parsed = parse_oge_asset_semantics("BGC GROUP, INC. (Class A)")
    assert parsed.quality == "accepted"
    assert parsed.asset_name == "BGC GROUP, INC. (Class A)"
    assert parsed.category == "股票/上市证券"
