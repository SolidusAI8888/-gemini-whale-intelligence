from __future__ import annotations

from datetime import date, datetime
import math
from typing import Mapping

CATEGORY_INFO_ADVANTAGE = {
    "CEO": 95,
    "CFO": 88,
    "Corporate Officer": 78,
    "Director": 72,
    "10% Owner": 82,
    "Corporate Insider": 65,
    "Congress": 75,
    "Political Whale:House": 86,
    "Political Whale:Senate": 90,
    "Government Official": 80,
    "Institutional Investor": 60,
}

ACTION_MULTIPLIER = {
    "BUY": 1.0,
    "SELL": 0.82,
    "GRANT_OR_AWARD": 0.18,
    "DISPOSITION_TO_ISSUER": 0.25,
    "OPTION_EXERCISE_OR_CONVERSION": 0.20,
    "TAX_WITHHOLDING_OR_PAYMENT": 0.12,
    "GIFT": 0.10,
    "OTHER": 0.05,
}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def capital_size_score(amount_usd: float | None) -> float:
    if not amount_usd or amount_usd <= 0:
        return 20.0
    # $10k≈20, $100k≈40, $1m≈60, $10m≈80, $100m≈100
    return clamp(20 + 20 * (math.log10(amount_usd) - 4))


def freshness_score(filing_date: str | None) -> float:
    dt = parse_date(filing_date)
    if dt is None:
        return 40.0
    days = max((date.today() - dt).days, 0)
    if days <= 1:
        return 100.0
    if days <= 3:
        return 90.0
    if days <= 7:
        return 75.0
    if days <= 30:
        return 55.0
    return 30.0


def calculate_trade_whale_score(trade: Mapping) -> float:
    category = str(trade.get("whale_category") or "Corporate Insider")
    info_advantage = CATEGORY_INFO_ADVANTAGE.get(category, 60)
    capital = capital_size_score(trade.get("amount_usd"))
    freshness = freshness_score(trade.get("filing_date"))
    action = str(trade.get("action") or "OTHER")
    action_strength = ACTION_MULTIPLIER.get(action, 0.05) * 100

    # MVP does not yet know each whale's 5-year historical alpha, so use a neutral prior.
    historical_accuracy = 50.0
    concentration = 50.0 if trade.get("amount_usd") is None else capital

    score = (
        info_advantage * 0.30
        + historical_accuracy * 0.15
        + capital * 0.20
        + concentration * 0.15
        + freshness * 0.10
        + action_strength * 0.10
    )
    return round(clamp(score), 2)
