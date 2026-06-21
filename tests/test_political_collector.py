from app.collectors.congress import _amount_midpoint, _normalize_action, _extract_ticker


def test_amount_range_midpoint():
    assert _amount_midpoint('$1,001 - $15,000') == 8000
    assert _amount_midpoint('$100,001 - $250,000') == 175000


def test_action_normalization():
    assert _normalize_action('Purchase')[0] == 'BUY'
    assert _normalize_action('Sale (Full)')[0] == 'SELL'


def test_extract_ticker_from_parentheses():
    assert _extract_ticker('Apple Inc. (AAPL) Purchase $1,001 - $15,000', {'AAPL'}) == 'AAPL'
