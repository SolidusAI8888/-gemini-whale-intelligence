from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping

from app.analyzers.whale_score import calculate_trade_whale_score, clamp

HIGH_SIGNAL_ACTIONS = {"BUY", "SELL"}


def _economic_key(row: Mapping) -> tuple[str, ...]:
    """Key for one underlying economic trade line.

    SEC Form 4 joint filings often list the same purchase/sale under multiple
    reporting owners in the same accession.  Counting each reporting owner as a
    separate dollar trade can multiply the true economic amount.  This key keeps
    split lots with different prices/amounts separate, while collapsing exact
    duplicate economic lines that differ only by reporting owner.
    """
    return (
        str(row.get("ticker") or "").upper(),
        str(row.get("action") or "").upper(),
        str(row.get("transaction_code") or ""),
        str(row.get("trade_date") or ""),
        str(row.get("filing_date") or ""),
        str(row.get("accession_number") or row.get("filing_url") or row.get("source_id") or ""),
        f"{float(row.get('amount_usd') or 0):.4f}",
        f"{float(row.get('shares') or 0):.4f}",
        f"{float(row.get('price') or 0):.4f}",
        str(row.get("source") or ""),
    )


def _unique_key(row: Mapping) -> tuple[str, str, str, str]:
    """Collapse split lots from one form/action into one consensus unit."""
    return (
        str(row.get("whale_name") or ""),
        str(row.get("accession_number") or row.get("filing_url") or ""),
        str(row.get("action") or ""),
        str(row.get("trade_date") or ""),
    )


def _economic_rows(rows: list[Mapping]) -> list[Mapping]:
    seen: dict[tuple[str, ...], Mapping] = {}
    for row in rows:
        seen.setdefault(_economic_key(row), row)
    return list(seen.values())


def build_consensus_scores(trades: Iterable[Mapping]) -> list[dict]:
    grouped: dict[str, list[Mapping]] = defaultdict(list)
    for trade in trades:
        ticker = str(trade.get("ticker") or "").upper()
        action = str(trade.get("action") or "")
        if ticker and action in HIGH_SIGNAL_ACTIONS:
            grouped[ticker].append(trade)

    results: list[dict] = []
    for ticker, rows in grouped.items():
        buy_rows = [r for r in rows if r.get("action") == "BUY"]
        sell_rows = [r for r in rows if r.get("action") == "SELL"]
        if not buy_rows and not sell_rows:
            continue

        buy_economic = _economic_rows(buy_rows)
        sell_economic = _economic_rows(sell_rows)

        unique_buy_whales = {str(r.get("whale_name")) for r in buy_rows}
        unique_sell_whales = {str(r.get("whale_name")) for r in sell_rows}
        unique_buy_categories = {str(r.get("whale_category")) for r in buy_rows}
        unique_sell_categories = {str(r.get("whale_category")) for r in sell_rows}
        unique_buy_events = {_unique_key(r) for r in buy_rows}
        unique_sell_events = {_unique_key(r) for r in sell_rows}

        # Economic amounts are de-duplicated across joint reporters.  Raw row
        # counts remain visible separately for auditability.
        buy_amount = sum(float(r.get("amount_usd") or 0) for r in buy_economic)
        sell_amount = sum(float(r.get("amount_usd") or 0) for r in sell_economic)
        trade_scores = [calculate_trade_whale_score(r) for r in rows]
        buy_scores = [calculate_trade_whale_score(r) for r in buy_economic]
        sell_scores = [calculate_trade_whale_score(r) for r in sell_economic]

        buy_consensus = clamp(
            len(unique_buy_whales) * 16
            + len(unique_buy_categories) * 8
            + min(len(unique_buy_events), 6) * 8
            + min(len(buy_economic), 10) * 1.5
        )
        sell_consensus = clamp(
            len(unique_sell_whales) * 14
            + len(unique_sell_categories) * 7
            + min(len(unique_sell_events), 6) * 6
            + min(len(sell_economic), 10) * 1.0
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
                "buy_economic_count": len(buy_economic),
                "sell_economic_count": len(sell_economic),
                "buy_amount": buy_amount,
                "sell_amount": sell_amount,
                "unique_buy_whales": len(unique_buy_whales),
                "unique_sell_whales": len(unique_sell_whales),
                "unique_buy_categories": len(unique_buy_categories),
                "unique_sell_categories": len(unique_sell_categories),
                "unique_buy_events": len(unique_buy_events),
                "unique_sell_events": len(unique_sell_events),
                "buy_score": buy_score,
                "sell_score": sell_score,
                "whale_score": whale_score,
                "consensus_score": round(consensus_score, 2),
                "net_direction": net_direction,
            }
        )
    return results
