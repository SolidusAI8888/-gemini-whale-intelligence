from __future__ import annotations

from typing import Iterable
from app.intelligence.models import WISScore


def build_rankings(scores: Iterable[WISScore], top_n: int = 10) -> dict[str, list[dict]]:
    rows = list(scores)
    opportunities = sorted(rows, key=lambda x: (-x.opportunity_score, -x.confidence, x.ticker))[:top_n]
    risks = sorted(rows, key=lambda x: (-x.risk_score, -x.confidence, x.ticker))[:top_n]
    resonance = sorted(rows, key=lambda x: (-x.resonance_score, -x.confidence, x.ticker))[:top_n]
    return {
        "opportunities": [x.to_dict() for x in opportunities],
        "risks": [x.to_dict() for x in risks],
        "resonance": [x.to_dict() for x in resonance],
    }
