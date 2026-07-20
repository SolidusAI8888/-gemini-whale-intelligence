from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
from typing import Iterable

from app.intelligence.config import WISConfig, load_wis_config
from app.intelligence.models import Signal, SignalDirection, SignalSource, WISScore
from app.intelligence.registry import DEFAULT_REGISTRY
from app.intelligence.resonance import calculate_resonance


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _age_days(value: str) -> int:
    try:
        return max(0, (date.today() - datetime.strptime(value[:10], "%Y-%m-%d").date()).days)
    except Exception:
        return 365


def _signal_strength(signal: Signal, max_age_days: int) -> float:
    recency = max(0.0, 1.0 - _age_days(signal.event_date) / max_age_days)
    amount = min(1.0, math.log10(max(signal.amount_usd, 1.0)) / 9.0)
    actor = DEFAULT_REGISTRY.get(signal.actor, signal.actor_category)
    base = (0.50 * signal.confidence + 0.30 * recency + 0.20 * amount) * actor.influence
    return _clamp(base * 100.0)


def _source_score(signals: list[Signal], source: SignalSource, max_age_days: int) -> float:
    rows = [s for s in signals if s.source is source]
    if not rows:
        return 50.0
    bullish = sum(_signal_strength(s, max_age_days) for s in rows if s.direction is SignalDirection.BULLISH)
    bearish = sum(_signal_strength(s, max_age_days) for s in rows if s.direction is SignalDirection.BEARISH)
    total = bullish + bearish
    if total <= 0:
        return 50.0
    directional = 50.0 + 50.0 * ((bullish - bearish) / total)
    breadth = min(10.0, len({s.actor for s in rows}) * 2.0)
    return _clamp(directional + (breadth if directional >= 50 else -breadth))


def score_signals(signals: Iterable[Signal], config: WISConfig | None = None) -> list[WISScore]:
    cfg = config or load_wis_config()
    grouped: dict[str, list[Signal]] = defaultdict(list)
    for signal in signals:
        if signal.amount_usd >= cfg.minimum_amount_usd:
            grouped[signal.ticker].append(signal)

    out: list[WISScore] = []
    for ticker, rows in grouped.items():
        form4 = _source_score(rows, SignalSource.FORM4, cfg.max_signal_age_days)
        institutional = _source_score(rows, SignalSource.INSTITUTIONAL_13F, cfg.max_signal_age_days)
        political_rows = [s for s in rows if s.source in {SignalSource.CONGRESS, SignalSource.OGE}]
        congress = _source_score(political_rows, SignalSource.CONGRESS, cfg.max_signal_age_days) if political_rows else 50.0
        if political_rows and all(s.source is SignalSource.OGE for s in political_rows):
            # OGE is part of the political/executive pillar.
            synthetic = [Signal(**{**s.__dict__, "source": SignalSource.CONGRESS}) for s in political_rows]
            congress = _source_score(synthetic, SignalSource.CONGRESS, cfg.max_signal_age_days)

        resonance, level, resonant_sources = calculate_resonance(rows)
        resonance_direction = 1.0 if sum(s.direction is SignalDirection.BULLISH for s in rows) >= sum(s.direction is SignalDirection.BEARISH for s in rows) else -1.0
        resonance_component = 50.0 + resonance_direction * resonance / 2.0
        w = cfg.weights
        wis = _clamp(form4 * w.form4 + institutional * w.institutional + congress * w.congress + resonance_component * w.resonance)
        opportunity = wis
        risk = 100.0 - wis
        confidence = _clamp(35.0 + len({s.source.value for s in rows}) * 15.0 + min(20.0, len({s.actor for s in rows}) * 2.0))
        momentum = _clamp(sum(_signal_strength(s, cfg.max_signal_age_days) * (1 if s.direction is SignalDirection.BULLISH else -1) for s in rows) / max(1, len(rows)) + 50.0)
        actors = sorted({s.actor for s in rows}, key=lambda a: (-sum(1 for s in rows if s.actor == a), a))[:5]
        sources = sorted({s.source.value for s in rows})
        explanation = f"Form4={form4:.1f}; 13F={institutional:.1f}; Congress/OGE={congress:.1f}; Resonance=L{level}({resonance:.1f}); actors={', '.join(actors)}"
        out.append(WISScore(
            ticker=ticker,
            wis_score=round(wis, 2),
            opportunity_score=round(opportunity, 2),
            risk_score=round(risk, 2),
            confidence=round(confidence, 2),
            momentum=round(momentum, 2),
            form4_score=round(form4, 2),
            institutional_score=round(institutional, 2),
            congress_score=round(congress, 2),
            resonance_score=round(resonance, 2),
            resonance_level=level,
            sources=sources,
            major_actors=actors,
            explanation=explanation,
        ))
    return sorted(out, key=lambda x: (-x.wis_score, -x.confidence, x.ticker))
