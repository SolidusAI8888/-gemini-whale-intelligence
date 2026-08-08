from app.reports.v40_oge import build_cabinet_oge_radar, passes_v42_report_gate_for_tests


def _row(asset_name: str) -> dict:
    return {
        "source_id": f"test:{asset_name}",
        "ticker": "OGE-ASSET",
        "company_name": asset_name,
        "filing_url": "https://example.com/report.pdf",
        "whale_name": "Official",
        "insider_role": "Cabinet",
        "action": "HOLDING",
        "transaction_code": "H",
        "amount_usd": 1_000_000,
        "trade_date": "2026-01-01",
        "filing_date": "2026-01-01",
        "source": "OGE_EXECUTIVE_ASSET",
        "raw_json": {"asset_name": asset_name, "amount_range_label": "$500,001–$1,000,000"},
    }


def test_v42_report_gate_blocks_legacy_noise():
    rejected = [
        "Over $50,000,000",
        "Dividends $100,001",
        "Crop Sales $51,180",
        "Interest $25,000",
        "RATE TERM 1",
        "On Demand",
        "# EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE",
    ]
    for value in rejected:
        assert passes_v42_report_gate_for_tests(value) is False


def test_v42_report_gate_accepts_real_assets():
    accepted = [
        "Bank of America, N.A.",
        "Cantor Fitzgerald, L.P.",
        "BGC Group, Inc. (BGC)",
        "Newmark Group, Inc. (NMRK)",
    ]
    for value in accepted:
        assert passes_v42_report_gate_for_tests(value) is True


def test_cabinet_radar_never_renders_legacy_dirty_rows():
    rows = [
        _row("Dividends $100,001"),
        _row("Crop Sales $51,180"),
        _row("# EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE"),
        _row("Bank of America, N.A."),
    ]
    html = build_cabinet_oge_radar(rows)
    assert "Bank of America, N.A." in html
    assert "Dividends $100,001" not in html
    assert "Crop Sales $51,180" not in html
    assert "EMPLOYER OR PARTY" not in html
