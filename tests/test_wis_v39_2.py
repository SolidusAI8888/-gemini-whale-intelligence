from app.collectors.sec_13f import DEFAULT_INSTITUTIONAL_WHALES
from app.intelligence.models import Signal, SignalDirection, SignalSource
from app.intelligence.ranking import build_rankings
from app.intelligence.score_engine import score_signals
from app.intelligence.signal import canonical_ticker


def sig(ticker, source, direction, actor):
    return Signal(ticker, source, direction, actor, "test", "2026-07-22", 1_000_000, confidence=0.8)


def test_default_smart_money_universe_has_at_least_50_managers():
    assert len(DEFAULT_INSTITUTIONAL_WHALES) >= 50
    assert len({w.cik for w in DEFAULT_INSTITUTIONAL_WHALES}) == len(DEFAULT_INSTITUTIONAL_WHALES)


def test_dash_cusip_maps_to_ticker():
    assert canonical_ticker("CUSIP:25809K105") == "DASH"


def test_rankings_are_semantically_separated():
    scores = score_signals([
        sig("PYPL", SignalSource.FORM4, SignalDirection.BULLISH, "Insider"),
        sig("PYPL", SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
        sig("AAPL", SignalSource.FORM4, SignalDirection.BEARISH, "Insider"),
        sig("AAPL", SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
        sig("KLAC", SignalSource.FORM4, SignalDirection.BEARISH, "Insider"),
        sig("KLAC", SignalSource.CONGRESS, SignalDirection.BEARISH, "Member"),
    ])
    r = build_rankings(scores)
    assert [x["ticker"] for x in r["opportunities"]] == ["PYPL"]
    assert [x["ticker"] for x in r["risks"]] == ["KLAC"]
    assert [x["ticker"] for x in r["conflicted"]] == ["AAPL"]
