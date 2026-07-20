from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from app.intelligence.models import Signal, SignalDirection


def calculate_resonance(signals: Iterable[Signal]) -> tuple[float, int, list[str]]:
    rows = list(signals)
    bullish_sources = {s.source.value for s in rows if s.direction is SignalDirection.BULLISH}
    bearish_sources = {s.source.value for s in rows if s.direction is SignalDirection.BEARISH}
    dominant = bullish_sources if len(bullish_sources) >= len(bearish_sources) else bearish_sources
    n = len(dominant)
    level = 3 if n >= 4 else 2 if n == 3 else 1 if n == 2 else 0
    base = {0: 0.0, 1: 45.0, 2: 75.0, 3: 100.0}[level]
    conflict = len(bullish_sources & bearish_sources)
    score = max(0.0, base - conflict * 12.5)
    return round(score, 2), level, sorted(dominant)
