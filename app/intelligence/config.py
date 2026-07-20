from __future__ import annotations

from dataclasses import dataclass, field
import os


@dataclass(frozen=True)
class WISWeights:
    form4: float = 0.20
    institutional: float = 0.30
    congress: float = 0.20
    resonance: float = 0.30

    def validate(self) -> None:
        total = self.form4 + self.institutional + self.congress + self.resonance
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"WIS weights must sum to 1.0; got {total}")
        if min(self.form4, self.institutional, self.congress, self.resonance) < 0:
            raise ValueError("WIS weights cannot be negative")


@dataclass(frozen=True)
class WISConfig:
    weights: WISWeights = field(default_factory=WISWeights)
    top_n: int = 10
    max_signal_age_days: int = 365
    minimum_amount_usd: float = 0.0


def load_wis_config() -> WISConfig:
    weights = WISWeights(
        form4=float(os.getenv("WIS_WEIGHT_FORM4", "0.20")),
        institutional=float(os.getenv("WIS_WEIGHT_13F", "0.30")),
        congress=float(os.getenv("WIS_WEIGHT_CONGRESS", "0.20")),
        resonance=float(os.getenv("WIS_WEIGHT_RESONANCE", "0.30")),
    )
    weights.validate()
    return WISConfig(
        weights=weights,
        top_n=max(1, int(os.getenv("WIS_TOP_N", "10"))),
        max_signal_age_days=max(1, int(os.getenv("WIS_MAX_SIGNAL_AGE_DAYS", "365"))),
        minimum_amount_usd=max(0.0, float(os.getenv("WIS_MIN_AMOUNT_USD", "0"))),
    )
