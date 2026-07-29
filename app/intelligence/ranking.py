from __future__ import annotations

from typing import Iterable
from app.intelligence.models import WISScore


def _opportunity_eligible(score: WISScore) -> bool:
    return (
        score.coverage_count >= 2
        and score.resonance_direction == "BULLISH"
        and score.wis_score > 55
        and score.opportunity_score >= 50
    )


def _risk_eligible(score: WISScore) -> bool:
    return score.resonance_direction == "BEARISH" or (
        score.resonance_direction == "NONE" and score.wis_score < 35 and score.risk_score >= 45
    )


def _conflicted_eligible(score: WISScore) -> bool:
    return score.resonance_direction == "CONFLICTED"


def build_rankings(scores: Iterable[WISScore], top_n: int = 10) -> dict[str, list[dict]]:
    rows = list(scores)
    opportunities = sorted(
        (x for x in rows if _opportunity_eligible(x)),
        key=lambda x: (-x.opportunity_score, -x.confidence, x.ticker),
    )[:top_n]
    risks = sorted(
        (x for x in rows if _risk_eligible(x)),
        key=lambda x: (-x.risk_score, -x.confidence, x.ticker),
    )[:top_n]
    conflicted = sorted(
        (x for x in rows if _conflicted_eligible(x)),
        key=lambda x: (-x.confidence, -abs(x.resonance_signed_score), x.ticker),
    )[:top_n]
    resonance = sorted(
        (x for x in rows if x.resonance_level > 0 and x.resonance_direction != "CONFLICTED"),
        key=lambda x: (-abs(x.resonance_signed_score), -x.confidence, x.ticker),
    )[:top_n]
    return {
        "opportunities": [x.to_dict() for x in opportunities],
        "risks": [x.to_dict() for x in risks],
        "conflicted": [x.to_dict() for x in conflicted],
        "resonance": [x.to_dict() for x in resonance],
    }
