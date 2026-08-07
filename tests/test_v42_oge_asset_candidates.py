from app.collectors.oge_asset_candidates import evaluate_oge_asset_candidate, extract_oge_asset_candidates


def test_v42_rejects_amount_income_and_financing_cells():
    rejected = [
        "Over $50,000,000",
        "Dividends $100,001",
        "Crop Sales $51,180",
        "Interest $25,000",
        "RATE TERM 1",
        "On Demand",
        "Government guaranteed collateral)",
    ]
    for raw in rejected:
        candidate = evaluate_oge_asset_candidate(raw)
        assert candidate.quality == "rejected"
        assert candidate.asset_name == ""


def test_v42_extracts_real_assets_and_dedupes_table_windows():
    lines = [
        "RATE TERM 1 Bank of America, N.A Secured Facility Over $50,000,000",
        "N/A On Demand 3 Bank of America, N.A Over $50,000,000",
        "Dividends $100,001",
        "14.6 Cantor Fitzgerald, L.P. See Endnote Over $50,000,000",
        "HWL Personal Asset Trust No 2.1 BGC Group, Inc. (BGC) Over $50,000,000",
        "Crop Sales $51,180",
    ]

    candidates = extract_oge_asset_candidates(lines)
    names = {candidate.asset_name for candidate in candidates}

    assert "Bank of America, N.A." in names
    assert "Cantor Fitzgerald, L.P." in names
    assert "BGC Group, Inc. (BGC)" in names
    assert all("Dividends" not in name for name in names)
    assert all("Crop Sales" not in name for name in names)
    assert len([name for name in names if name.startswith("Bank of America")]) == 1


def test_v42_repairs_split_asset_row_without_accepting_amount_cell():
    lines = [
        "DFI Smith Follett Crowl, LLC",
        "$1,000,001 - $5,000,000",
        "Rent or Royalties $50,001",
    ]

    candidates = extract_oge_asset_candidates(lines)
    assert [candidate.asset_name for candidate in candidates] == ["DFI Smith Follett Crowl, LLC"]
