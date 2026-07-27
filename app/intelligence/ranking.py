from __future__ import annotations

from typing import Iterable
from app.intelligence.models import WISScore


def _opportunity_eligible(score: WISScore) -> bool:
    # Normal path requires two independent pillars. A single very strong pillar may
    # enter only when the score and confidence are both exceptional; it remains
    # explicitly marked Low Coverage in the report.
    return score.coverage_count >= 2 or (
        score.coverage_count == 1
        and score.opportunity_score >= 85
        and score.confidence >= 80
        and score.signal_count >= 10
        and score.freshness_days is not None
        and score.freshness_days <= 14
    )


def build_rankings(scores: Iterable[WISScore], top_n: int = 10) -> dict[str, list[dict]]:
    rows = list(scores)
    opportunities = sorted(
        (x for x in rows if _opportunity_eligible(x)),
        key=lambda x: (-x.opportunity_score, -x.confidence, x.ticker),
    )[:top_n]
    risks = sorted(rows, key=lambda x: (-x.risk_score, -x.confidence, x.ticker))[:top_n]
    resonance = sorted(
        (x for x in rows if x.resonance_level > 0),
        key=lambda x: (-abs(x.resonance_signed_score), -x.confidence, x.ticker),
    )[:top_n]
    return {
        "opportunities": [x.to_dict() for x in opportunities],
        "risks": [x.to_dict() for x in risks],
        "resonance": [x.to_dict() for x in resonance],
    }
