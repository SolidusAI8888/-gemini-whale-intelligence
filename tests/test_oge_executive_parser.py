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



def test_parse_oge_repairs_future_date_and_amount_range():
    text = """
    Transactions are held in a discretionary managed account.
    BROADCOM INC COM purchase 02/10/2028 $1 - $5,000,000
    """
    rows = parse_oge_text_for_tests(
        text=text,
        filer_name="Donald J. Trump",
        position="President",
        agency="White House",
        source_url="https://example.gov/trump-278t.pdf",
    )
    assert rows[0]["ticker"] == "AVGO"
    assert rows[0]["trade_date"] == "2026-02-10"
    assert rows[0]["amount_usd"] == 3_000_000.5
    assert "corrected_future_date" in rows[0]["raw_json"]


def test_parse_oge_quarantines_malformed_single_amount_fragment():
    text = """
    Microsoft Corporation purchase 01/06/2026 $1 - $1
    """
    rows = parse_oge_text_for_tests(
        text=text,
        filer_name="Donald J. Trump",
        position="President",
        agency="White House",
        source_url="https://example.gov/trump-278t.pdf",
    )
    assert rows == []
