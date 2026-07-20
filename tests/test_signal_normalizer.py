from app.intelligence.models import SignalDirection, SignalSource
from app.intelligence.signal import normalize_trade


def test_form4_buy_normalizes():
    row = {"ticker":"MSFT","source":"SEC_FORM4","action":"BUY","whale_name":"CEO","whale_category":"Business Insider","trade_date":"2026-07-18","amount_usd":1000}
    signal = normalize_trade(row)
    assert signal is not None
    assert signal.source is SignalSource.FORM4
    assert signal.direction is SignalDirection.BULLISH


def test_cusip_only_is_excluded():
    assert normalize_trade({"ticker":"CUSIP:123", "source":"INSTITUTIONAL_13F", "action":"BUY"}) is None
