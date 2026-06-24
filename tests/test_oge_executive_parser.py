from app.collectors.oge_executive import parse_oge_text_for_tests


def test_parse_oge_278t_sample_block():
    text = """
    Filer paid late fees. Transactions are held in a discretionary managed account.
    NVIDIA Corporation (NVDA) Purchase 01/15/2026 $1,001 - $15,000
    Microsoft Corporation (MSFT) Sale 02/02/2026 $5,000,001 - $25,000,000
    """
    rows = parse_oge_text_for_tests(
        text=text,
        filer_name="Donald J. Trump",
        position="President",
        agency="White House",
        source_url="https://example.gov/trump-278t.pdf",
    )
    tickers = {r["ticker"]: r for r in rows}
    assert "NVDA" in tickers
    assert "MSFT" in tickers
    assert tickers["NVDA"]["action"] == "BUY"
    assert tickers["MSFT"]["action"] == "SELL"
    assert tickers["MSFT"]["amount_usd"] == 15_000_000.5
    assert tickers["MSFT"]["source"] == "OGE_EXECUTIVE_TRUMP"
    assert "late_fee_flag" in tickers["NVDA"]["raw_json"]
