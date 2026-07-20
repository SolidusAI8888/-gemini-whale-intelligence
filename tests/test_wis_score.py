from app.intelligence.config import WISConfig, WISWeights
from app.intelligence.models import Signal, SignalDirection, SignalSource
from app.intelligence.score_engine import score_signals


def s(source, direction, actor, amount=1_000_000):
    return Signal("AAPL", source, direction, actor, "test", "2026-07-18", amount)


def test_cross_source_bullish_scores_above_neutral():
    rows = [
        s(SignalSource.FORM4, SignalDirection.BULLISH, "CEO"),
        s(SignalSource.INSTITUTIONAL_13F, SignalDirection.BULLISH, "Fund"),
        s(SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
    ]
    score = score_signals(rows)[0]
    assert score.wis_score > 70
    assert score.resonance_level == 2
    assert score.risk_score < 30


def test_weights_are_frozen_to_v39_spec():
    w = WISWeights()
    assert (w.form4, w.institutional, w.congress, w.resonance) == (0.20, 0.30, 0.20, 0.30)
