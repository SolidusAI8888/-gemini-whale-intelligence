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

from app.collectors.oge_executive import parse_oge_asset_text_for_tests


def test_parse_oge_278e_asset_disclosure_as_holding_not_trade():
    text = """
    Executive Branch Personnel Public Financial Disclosure Report (OGE Form 278e)
    Acme Growth Fund, LLC Value $500,001 - $1,000,000 Income amount $15,001 - $50,000
    Commercial real estate, Denver, CO $1,000,001 - $5,000,000
    """
    rows = parse_oge_asset_text_for_tests(
        text=text,
        filer_name="Chris Wright",
        position="Secretary of Energy",
        agency="Energy",
        source_url="https://example.gov/wright-final278.pdf",
        report_type="OGE_278e",
    )
    assert rows
    assert all(r["action"] in {"HOLDING", "DISCLOSURE"} for r in rows)
    assert rows[0]["source"] == "OGE_EXECUTIVE_ASSET"
    assert "not a recent BUY/SELL trade" in rows[0]["raw_json"]
