from __future__ import annotations

from app.analyzers.whale_score import clamp


def signal_label(score: float, direction: str) -> str:
    prefix = "多头" if direction == "BUY" else "空头/减持"
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

    # V1 intentionally leaves sector/earnings/valuation/sentiment neutral until market-data connectors are added.
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
        f"买入记录={row['buy_count']} 笔/${row['buy_amount']:,.0f}; "
        f"卖出记录={row['sell_count']} 笔/${row['sell_amount']:,.0f}. "
        "V1 暂未接入基本面/估值/行情，因此这些维度采用中性先验。"
    )

    return {
        "ticker": row["ticker"],
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
