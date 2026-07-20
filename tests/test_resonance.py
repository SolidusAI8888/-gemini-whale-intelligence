from app.intelligence.models import Signal, SignalDirection, SignalSource
from app.intelligence.resonance import calculate_resonance


def test_three_sources_is_level_two():
    rows = [Signal("NVDA", src, SignalDirection.BULLISH, src.value, "x", "2026-07-18") for src in (SignalSource.FORM4, SignalSource.INSTITUTIONAL_13F, SignalSource.CONGRESS)]
    score, level, sources = calculate_resonance(rows)
    assert level == 2
    assert score == 75
    assert len(sources) == 3
