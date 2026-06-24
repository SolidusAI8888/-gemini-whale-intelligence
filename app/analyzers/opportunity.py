from __future__ import annotations

from app.analyzers.whale_score import clamp


def signal_label(score: float, direction: str) -> str:
    prefix = "多头" if direction == "BUY" else "减持/卖出预警"
    if score >= 85:
        return f"{prefix} S级"
    if score >= 75:
        return f"{prefix} A级"
    if score >= 65:
        return f"{prefix} B级"
    if score >= 55:
        return f"{prefix} 观察"
    return "噪音/低置信度"


def calculate_opportunity_score(row: dict) -> dict:
    direction = row["net_direction"]
    directional_score = row["buy_score"] if direction == "BUY" else row["sell_score"]
    opposite_score = row["sell_score"] if direction == "BUY" else row["buy_score"]
    consensus = row["consensus_score"]

    # V11 still keeps public-disclosure activity as the anchor. Market-data
    # connectors apply small transparent adjustments later.
    sector_score = 50.0
    earnings_score = 50.0
    valuation_score = 50.0
    sentiment_score = 50.0

    score = (
        directional_score * 0.40
        + consensus * 0.25
        + sector_score * 0.12
        + earnings_score * 0.08
        + valuation_score * 0.08
        + sentiment_score * 0.07
    )
    risk = clamp(opposite_score * 0.55 + (100 - consensus) * 0.20)
    final_score = clamp(score - max(0, opposite_score - directional_score) * 0.25)

    explanation = (
        f"方向={direction}; 共识分={consensus:.1f}; "
        f"买入记录={row['buy_count']} 笔，去重经济笔数={row.get('buy_economic_count', row['buy_count'])}，金额=${row['buy_amount']:,.0f}; "
        f"卖出记录={row['sell_count']} 笔，去重经济笔数={row.get('sell_economic_count', row['sell_count'])}，金额=${row['sell_amount']:,.0f}; "
        f"独立买入事件={row.get('unique_buy_events', 0)}; 独立卖出事件={row.get('unique_sell_events', 0)}. "
        "行情/基本面/情绪若有配置，会在后续步骤小幅调整机会分。"
    )

    return {
        "ticker": row["ticker"],
        "buy_count": row.get("buy_count", 0),
        "sell_count": row.get("sell_count", 0),
        "buy_economic_count": row.get("buy_economic_count", row.get("buy_count", 0)),
        "sell_economic_count": row.get("sell_economic_count", row.get("sell_count", 0)),
        "buy_amount": float(row.get("buy_amount") or 0),
        "sell_amount": float(row.get("sell_amount") or 0),
        "unique_buy_events": row.get("unique_buy_events", 0),
        "unique_sell_events": row.get("unique_sell_events", 0),
        "unique_buy_whales": row.get("unique_buy_whales", 0),
        "unique_sell_whales": row.get("unique_sell_whales", 0),
        "buy_score": row["buy_score"],
        "sell_score": row["sell_score"],
        "whale_score": row["whale_score"],
        "consensus_score": consensus,
        "opportunity_score": round(final_score, 2),
        "risk_score": round(risk, 2),
        "signal_label": signal_label(final_score, direction),
        "explanation": explanation,
    }


def score_opportunities(consensus_rows: list[dict]) -> list[dict]:
    scored = [calculate_opportunity_score(row) for row in consensus_rows]
    return sorted(scored, key=lambda r: r["opportunity_score"], reverse=True)
