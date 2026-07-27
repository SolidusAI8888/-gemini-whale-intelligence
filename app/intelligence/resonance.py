from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.intelligence.models import (
    ResonanceDirection,
    ResonanceResult,
    Signal,
    SignalDirection,
)


def calculate_resonance(signals: Iterable[Signal]) -> ResonanceResult:
    """Calculate signed, cross-source resonance.

    L0: no cross-source agreement
    L1: two agreeing source pillars
    L2: three agreeing source pillars
    L3: four agreeing source pillars

    The absolute score measures agreement strength; signed_score preserves direction.
    Mixed bullish and bearish source pillars are marked CONFLICTED.
    """
    rows = list(signals)
    by_source: dict[str, dict[SignalDirection, float]] = defaultdict(lambda: defaultdict(float))
    for signal in rows:
        if signal.direction is SignalDirection.NEUTRAL:
            continue
        # Confidence and transaction size are intentionally not used here: resonance
        # measures independent source agreement, while strength is handled by WIS.
        by_source[signal.source.value][signal.direction] += max(0.0, signal.confidence)

    bullish_sources: set[str] = set()
    bearish_sources: set[str] = set()
    for source, values in by_source.items():
        bull = values.get(SignalDirection.BULLISH, 0.0)
        bear = values.get(SignalDirection.BEARISH, 0.0)
        if bull > bear:
            bullish_sources.add(source)
        elif bear > bull:
            bearish_sources.add(source)
        elif bull > 0:
            bullish_sources.add(source)
            bearish_sources.add(source)

    bull_n, bear_n = len(bullish_sources), len(bearish_sources)
    dominant_n = max(bull_n, bear_n)
    level = 3 if dominant_n >= 4 else 2 if dominant_n == 3 else 1 if dominant_n == 2 else 0
    base = {0: 0.0, 1: 45.0, 2: 75.0, 3: 100.0}[level]

    if not bullish_sources and not bearish_sources:
        direction = ResonanceDirection.NONE
        signed = 0.0
        sources: set[str] = set()
    elif bullish_sources and bearish_sources:
        direction = ResonanceDirection.CONFLICTED
        # Penalize cross-direction disagreement, but keep a small signed lean.
        conflict_penalty = min(50.0, min(bull_n, bear_n) * 20.0)
        score = max(0.0, base - conflict_penalty)
        lean = 1.0 if bull_n > bear_n else -1.0 if bear_n > bull_n else 0.0
        signed = score * lean
        sources = bullish_sources | bearish_sources
        return ResonanceResult(
            score=round(score, 2), signed_score=round(signed, 2), level=level,
            direction=direction, sources=sorted(sources),
            bullish_sources=sorted(bullish_sources), bearish_sources=sorted(bearish_sources),
        )
    elif bullish_sources:
        direction = ResonanceDirection.BULLISH
        signed = base
        sources = bullish_sources
    else:
        direction = ResonanceDirection.BEARISH
        signed = -base
        sources = bearish_sources

    return ResonanceResult(
        score=round(abs(signed), 2), signed_score=round(signed, 2), level=level,
        direction=direction, sources=sorted(sources),
        bullish_sources=sorted(bullish_sources), bearish_sources=sorted(bearish_sources),
    )
