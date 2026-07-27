from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
from typing import Iterable

from app.intelligence.config import WISConfig, load_wis_config
from app.intelligence.models import Signal, SignalDirection, SignalSource, WISScore
from app.intelligence.registry import DEFAULT_REGISTRY
from app.intelligence.resonance import calculate_resonance

PILLAR_NAMES = ("FORM4", "13F", "CONGRESS_OGE")


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


def _source_score(signals: list[Signal], source: SignalSource, max_age_days: int) -> float | None:
    rows = [s for s in signals if s.source is source]
    if not rows:
        return None
    bullish = sum(_signal_strength(s, max_age_days) for s in rows if s.direction is SignalDirection.BULLISH)
    bearish = sum(_signal_strength(s, max_age_days) for s in rows if s.direction is SignalDirection.BEARISH)
    total = bullish + bearish
    if total <= 0:
        return None
    directional = 50.0 + 50.0 * ((bullish - bearish) / total)
    breadth = min(10.0, len({s.actor for s in rows}) * 2.0)
    return _clamp(directional + (breadth if directional >= 50 else -breadth))


def _political_score(rows: list[Signal], max_age_days: int) -> float | None:
    political = [s for s in rows if s.source in {SignalSource.CONGRESS, SignalSource.OGE}]
    if not political:
        return None
    synthetic = [Signal(**{**s.__dict__, "source": SignalSource.CONGRESS}) for s in political]
    return _source_score(synthetic, SignalSource.CONGRESS, max_age_days)


def _dynamic_weighted_average(components: list[tuple[float | None, float]]) -> float:
    available = [(score, weight) for score, weight in components if score is not None and weight > 0]
    if not available:
        return 50.0
    denominator = sum(weight for _, weight in available)
    return _clamp(sum(float(score) * weight for score, weight in available) / denominator)


def _risk_score(rows: list[Signal], max_age_days: int, resonance_signed: float) -> float:
    """Independent downside-risk score; it is not the inverse of WIS."""
    bearish_strengths = [
        _signal_strength(s, max_age_days)
        for s in rows
        if s.direction is SignalDirection.BEARISH
    ]
    bullish_strengths = [
        _signal_strength(s, max_age_days)
        for s in rows
        if s.direction is SignalDirection.BULLISH
    ]
    if not bearish_strengths:
        base = 8.0
    else:
        average = sum(bearish_strengths) / len(bearish_strengths)
        breadth = len({s.source.value for s in rows if s.direction is SignalDirection.BEARISH})
        actor_breadth = len({s.actor for s in rows if s.direction is SignalDirection.BEARISH})
        base = 0.55 * average + min(22.0, breadth * 7.0) + min(15.0, actor_breadth * 2.0)
    if resonance_signed < 0:
        base += min(25.0, abs(resonance_signed) * 0.25)
    if bullish_strengths:
        base -= min(20.0, (sum(bullish_strengths) / len(bullish_strengths)) * 0.20)
    return _clamp(base)


def _confidence(coverage_ratio: float, signal_count: int, freshness_days: int | None, rows: list[Signal]) -> float:
    freshness = 0.0 if freshness_days is None else max(0.0, 1.0 - freshness_days / 365.0)
    count_factor = min(1.0, math.log1p(signal_count) / math.log(21.0))
    avg_signal_conf = sum(max(0.0, min(1.0, s.confidence)) for s in rows) / max(1, len(rows))
    return _clamp((0.45 * coverage_ratio + 0.25 * count_factor + 0.20 * freshness + 0.10 * avg_signal_conf) * 100.0)


def _freshness_label(days: int | None) -> str:
    if days is None:
        return "N/A"
    if days == 0:
        return "Today"
    if days == 1:
        return "1 day"
    return f"{days} days"


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
        congress = _political_score(rows, cfg.max_signal_age_days)

        resonance = calculate_resonance(rows)
        resonance_component = 50.0 + resonance.signed_score / 2.0
        w = cfg.weights
        wis = _dynamic_weighted_average([
            (form4, w.form4),
            (institutional, w.institutional),
            (congress, w.congress),
            (resonance_component if resonance.level > 0 else None, w.resonance),
        ])

        effective_sources = []
        if form4 is not None:
            effective_sources.append("FORM4")
        if institutional is not None:
            effective_sources.append("13F")
        if congress is not None:
            effective_sources.append("CONGRESS_OGE")
        coverage_count = len(effective_sources)
        coverage_total = len(PILLAR_NAMES)
        coverage_ratio = coverage_count / coverage_total
        freshness_days = min((_age_days(s.event_date) for s in rows), default=None)
        confidence = _confidence(coverage_ratio, len(rows), freshness_days, rows)
        risk = _risk_score(rows, cfg.max_signal_age_days, resonance.signed_score)
        momentum = _clamp(sum(
            _signal_strength(s, cfg.max_signal_age_days) * (1 if s.direction is SignalDirection.BULLISH else -1)
            for s in rows
        ) / max(1, len(rows)) + 50.0)
        actors = sorted({s.actor for s in rows}, key=lambda a: (-sum(1 for s in rows if s.actor == a), a))[:5]
        raw_sources = sorted({s.source.value for s in rows})
        low_coverage = coverage_count < 2

        def fmt(value: float | None) -> str:
            return "N/A" if value is None else f"{value:.1f}"

        explanation = (
            f"Form4={fmt(form4)}; 13F={fmt(institutional)}; Congress/OGE={fmt(congress)}; "
            f"Coverage={coverage_count}/{coverage_total}; Confidence={confidence:.0f}%; "
            f"Freshness={_freshness_label(freshness_days)}; "
            f"Resonance={resonance.direction.value}/L{resonance.level}({resonance.signed_score:+.1f}); "
            f"actors={', '.join(actors)}"
        )
        out.append(WISScore(
            ticker=ticker,
            wis_score=round(wis, 2),
            opportunity_score=round(wis, 2),
            risk_score=round(risk, 2),
            confidence=round(confidence, 2),
            momentum=round(momentum, 2),
            form4_score=None if form4 is None else round(form4, 2),
            institutional_score=None if institutional is None else round(institutional, 2),
            congress_score=None if congress is None else round(congress, 2),
            resonance_score=round(resonance.score, 2),
            resonance_signed_score=round(resonance.signed_score, 2),
            resonance_level=resonance.level,
            resonance_direction=resonance.direction.value,
            resonance_sources=resonance.sources,
            sources=raw_sources,
            effective_sources=effective_sources,
            coverage_count=coverage_count,
            coverage_total=coverage_total,
            coverage_ratio=round(coverage_ratio, 4),
            coverage_label=f"{coverage_count}/{coverage_total} Sources",
            signal_count=len(rows),
            freshness_days=freshness_days,
            freshness_label=_freshness_label(freshness_days),
            low_coverage=low_coverage,
            major_actors=actors,
            explanation=explanation,
        ))
    return sorted(out, key=lambda x: (-x.wis_score, -x.confidence, x.ticker))
