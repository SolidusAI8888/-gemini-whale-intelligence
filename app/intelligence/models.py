from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Any


class SignalSource(str, Enum):
    FORM4 = "FORM4"
    CONGRESS = "CONGRESS"
    OGE = "OGE"
    INSTITUTIONAL_13F = "13F"


class SignalDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class Signal:
    ticker: str
    source: SignalSource
    direction: SignalDirection
    actor: str
    actor_category: str
    event_date: str
    amount_usd: float = 0.0
    action: str = ""
    confidence: float = 0.5
    source_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["source"] = self.source.value
        data["direction"] = self.direction.value
        return data


@dataclass
class WISScore:
    ticker: str
    wis_score: float
    opportunity_score: float
    risk_score: float
    confidence: float
    momentum: float
    form4_score: float
    institutional_score: float
    congress_score: float
    resonance_score: float
    resonance_level: int
    sources: list[str]
    major_actors: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
