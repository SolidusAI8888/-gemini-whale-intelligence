from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from app.analyzers.whale_score import calculate_trade_whale_score, clamp


def build_consensus_scores(trades: Iterable[Mapping]) -> list[dict]:
    grouped: dict[str, list[Mapping]] = defaultdict(list)
    for trade in trades:
        ticker = str(trade.get("ticker") or "").upper()
        if ticker:
            grouped[ticker].append(trade)

    results: list[dict] = []
    for ticker, rows in grouped.items():
        buy_rows = [r for r in rows if r.get("action") == "BUY"]
        sell_rows = [r for r in rows if r.get("action") == "SELL"]
        unique_buy_whales = {str(r.get("whale_name")) for r in buy_rows}
        unique_sell_whales = {str(r.get("whale_name")) for r in sell_rows}
        unique_buy_categories = {str(r.get("whale_category")) for r in buy_rows}
        unique_sell_categories = {str(r.get("whale_category")) for r in sell_rows}

        buy_amount = sum(float(r.get("amount_usd") or 0) for r in buy_rows)
        sell_amount = sum(float(r.get("amount_usd") or 0) for r in sell_rows)
        trade_scores = [calculate_trade_whale_score(r) for r in rows]
        buy_scores = [calculate_trade_whale_score(r) for r in buy_rows]
        sell_scores = [calculate_trade_whale_score(r) for r in sell_rows]

        # Independent sources and repeated whales both matter, with diminishing returns.
        buy_consensus = clamp(
            len(unique_buy_whales) * 18
            + len(unique_buy_categories) * 12
            + min(len(buy_rows), 8) * 4
        )
        sell_consensus = clamp(
            len(unique_sell_whales) * 18
            + len(unique_sell_categories) * 12
            + min(len(sell_rows), 8) * 4
        )

        whale_score = round(sum(trade_scores) / len(trade_scores), 2) if trade_scores else 0.0
        buy_score = round(sum(buy_scores) / len(buy_scores), 2) if buy_scores else 0.0
        sell_score = round(sum(sell_scores) / len(sell_scores), 2) if sell_scores else 0.0

        net_direction = "BUY" if buy_score + buy_consensus >= sell_score + sell_consensus else "SELL"
        consensus_score = buy_consensus if net_direction == "BUY" else sell_consensus

        results.append(
            {
                "ticker": ticker,
                "buy_count": len(buy_rows),
                "sell_count": len(sell_rows),
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
                "unique_buy_whales": len(unique_buy_whales),
                "unique_sell_whales": len(unique_sell_whales),
                "unique_buy_categories": len(unique_buy_categories),
                "unique_sell_categories": len(unique_sell_categories),
                "buy_score": buy_score,
                "sell_score": sell_score,
                "whale_score": whale_score,
                "consensus_score": round(consensus_score, 2),
                "net_direction": net_direction,
            }
        )
    return results
