from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.intelligence.models import ResonanceDirection, ResonanceResult, Signal, SignalDirection, SignalSource


def _pillar(signal: Signal) -> str:
    # Congress and Cabinet OGE form one political pillar. Counting them as two
    # independent pillars inflated resonance while coverage correctly showed 1/3.
    if signal.source in {SignalSource.CONGRESS, SignalSource.OGE}:
        return "CONGRESS_OGE"
    return signal.source.value


def calculate_resonance(signals: Iterable[Signal]) -> ResonanceResult:
    """Calculate signed agreement across the three independent WIS pillars.

    L0: fewer than two agreeing pillars (no cross-source resonance)
    L1: two agreeing pillars
    L2: all three pillars agree
    L3: all three pillars agree with broad actor confirmation (>= 6 actors)
    """
    rows = list(signals)
    by_pillar: dict[str, dict[SignalDirection, float]] = defaultdict(lambda: defaultdict(float))
    actors_by_pillar: dict[str, set[str]] = defaultdict(set)
    for signal in rows:
        if signal.direction is SignalDirection.NEUTRAL:
            continue
        pillar = _pillar(signal)
        by_pillar[pillar][signal.direction] += max(0.0, signal.confidence)
        actors_by_pillar[pillar].add(signal.actor)

    bullish: set[str] = set()
    bearish: set[str] = set()
    for pillar, values in by_pillar.items():
        bull = values.get(SignalDirection.BULLISH, 0.0)
        bear = values.get(SignalDirection.BEARISH, 0.0)
        if bull > bear:
            bullish.add(pillar)
        elif bear > bull:
            bearish.add(pillar)
        elif bull > 0:
            bullish.add(pillar)
            bearish.add(pillar)

    bull_n, bear_n = len(bullish), len(bearish)
    dominant_n = max(bull_n, bear_n)
    actor_count = len({s.actor for s in rows})
    if dominant_n < 2:
        level = 0
    elif dominant_n == 2:
        level = 1
    elif actor_count >= 6:
        level = 3
    else:
        level = 2
    base = {0: 0.0, 1: 45.0, 2: 75.0, 3: 100.0}[level]

    if not bullish and not bearish:
        direction, signed, sources = ResonanceDirection.NONE, 0.0, set()
    elif bullish and bearish:
        direction = ResonanceDirection.CONFLICTED
        sources = bullish | bearish
        # Conflicted signals are not "resonance" unless at least two pillars
        # agree on one side. Preserve a signed lean without granting single-source
        # conflicts a positive resonance contribution.
        score = max(0.0, base - min(50.0, min(bull_n, bear_n) * 20.0))
        lean = 1.0 if bull_n > bear_n else -1.0 if bear_n > bull_n else 0.0
        signed = score * lean
        return ResonanceResult(round(score, 2), round(signed, 2), level, direction, sorted(sources), sorted(bullish), sorted(bearish))
    elif bullish:
        direction, signed, sources = ResonanceDirection.BULLISH, base, bullish
    else:
        direction, signed, sources = ResonanceDirection.BEARISH, -base, bearish

    # A single directional pillar is a signal direction, not cross-source resonance.
    if level == 0:
        direction = ResonanceDirection.NONE
        signed = 0.0
    return ResonanceResult(round(abs(signed), 2), round(signed, 2), level, direction, sorted(sources), sorted(bullish), sorted(bearish))
