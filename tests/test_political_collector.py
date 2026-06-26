from app.collectors.congress import _amount_midpoint, _normalize_action, _extract_ticker


def test_amount_range_midpoint():
    assert _amount_midpoint('$1,001 - $15,000') == 8000
    assert _amount_midpoint('$100,001 - $250,000') == 175000


def test_action_normalization():
    assert _normalize_action('Purchase')[0] == 'BUY'
    assert _normalize_action('Sale (Full)')[0] == 'SELL'


def test_extract_ticker_from_parentheses():
    assert _extract_ticker('Apple Inc. (AAPL) Purchase $1,001 - $15,000', {'AAPL'}) == 'AAPL'


from app.collectors.congress import HouseFiling, _parse_house_pdf_transactions


def test_house_ptr_option_rows_keep_transaction_date_and_first_row():
    filing = HouseFiling(doc_id="20034836", filer="Nancy Pelosi", state_district="CA11", filing_type="P", filing_date="2026-06-23", year=2026)
    text = """
    Intel Corporation - Common Stock
    (INTC) [OP]
    P
    05/29/2026
    05/29/2026
    $1,000,001 - $5,000,000
    D: Purchased 200 call options with a strike price of $50 and an expiration date of 03/19/2027.
    Uber Technologies, Inc. Common Stock
    (UBER) [OP]
    P
    05/29/2026
    05/29/2026
    $500,001 - $1,000,000
    D: Purchased 200 call options with a strike price of $50 and an expiration date of 03/19/2027.
    """
    rows = _parse_house_pdf_transactions(filing, text, "https://example.gov/20034836.pdf", set())
    by_ticker = {r["ticker"]: r for r in rows}
    assert by_ticker["INTC"]["action"] == "BUY"
    assert by_ticker["INTC"]["trade_date"] == "2026-05-29"
    assert by_ticker["INTC"]["amount_usd"] == 3_000_000
    assert by_ticker["UBER"]["trade_date"] == "2026-05-29"
    assert "2027-03-19" in by_ticker["UBER"]["raw_json"]


def test_house_ptr_donor_advised_fund_not_core_sell():
    filing = HouseFiling(doc_id="20033725", filer="Nancy Pelosi", state_district="CA11", filing_type="P", filing_date="2026-01-23", year=2026)
    text = """
    Apple Inc. Common Stock
    (AAPL) [ST]
    S partial
    12/30/2025
    12/30/2025
    $5,000,001 - $25,000,000
    Contribution of 28,200 shares to Donor-Advised Fund.
    """
    rows = _parse_house_pdf_transactions(filing, text, "https://example.gov/20033725.pdf", set())
    assert rows[0]["ticker"] == "AAPL"
    assert rows[0]["action"] == "OTHER_TRANSFER"
    assert rows[0]["transaction_code"] == "G"
