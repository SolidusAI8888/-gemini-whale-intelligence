from __future__ import annotations

from dataclasses import asdict, dataclass, field
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


class ResonanceDirection(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    CONFLICTED = "CONFLICTED"
    NONE = "NONE"


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


@dataclass(frozen=True)
class ResonanceResult:
    score: float
    signed_score: float
    level: int
    direction: ResonanceDirection
    sources: list[str]
    bullish_sources: list[str]
    bearish_sources: list[str]

    def __iter__(self):
        """Backward-compatible unpacking: score, level, sources."""
        yield self.score
        yield self.level
        yield self.sources


@dataclass
class WISScore:
    ticker: str
    wis_score: float
    opportunity_score: float
    risk_score: float
    confidence: float
    momentum: float
    form4_score: float | None
    institutional_score: float | None
    congress_score: float | None
    resonance_score: float
    resonance_signed_score: float
    resonance_level: int
    resonance_direction: str
    resonance_sources: list[str]
    sources: list[str]
    effective_sources: list[str]
    coverage_count: int
    coverage_total: int
    coverage_ratio: float
    coverage_label: str
    signal_count: int
    freshness_days: int | None
    freshness_label: str
    low_coverage: bool
    major_actors: list[str]
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
