from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable, Mapping, Any

from app.config import settings

SCHEMA_PATH = Path("sql/schema.sql")


def get_conn() -> sqlite3.Connection:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_conn() as conn:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        conn.executescript(schema)
        conn.commit()


def upsert_trades(trades: Iterable[Mapping[str, Any]]) -> int:
    rows = list(trades)
    if not rows:
        return 0

    sql = """
    INSERT OR IGNORE INTO trades (
        source_id, ticker, company_name, cik, accession_number, filing_url,
        whale_name, whale_category, insider_role,
        action, transaction_code, amount_usd, shares, price,
        trade_date, filing_date, source, raw_json
    ) VALUES (
        :source_id, :ticker, :company_name, :cik, :accession_number, :filing_url,
        :whale_name, :whale_category, :insider_role,
        :action, :transaction_code, :amount_usd, :shares, :price,
        :trade_date, :filing_date, :source, :raw_json
    )
    """
    with get_conn() as conn:
        before = conn.total_changes
        conn.executemany(sql, rows)
        conn.commit()
        return conn.total_changes - before


def insert_scores(scores: Iterable[Mapping[str, Any]]) -> int:
    rows = list(scores)
    if not rows:
        return 0
    sql = """
    INSERT INTO scores (
        ticker, buy_score, sell_score, whale_score, consensus_score,
        opportunity_score, risk_score, signal_label, explanation, updated_at
    ) VALUES (
        :ticker, :buy_score, :sell_score, :whale_score, :consensus_score,
        :opportunity_score, :risk_score, :signal_label, :explanation, CURRENT_TIMESTAMP
    )
    ON CONFLICT(ticker) DO UPDATE SET
        buy_score=excluded.buy_score,
        sell_score=excluded.sell_score,
        whale_score=excluded.whale_score,
        consensus_score=excluded.consensus_score,
        opportunity_score=excluded.opportunity_score,
        risk_score=excluded.risk_score,
        signal_label=excluded.signal_label,
        explanation=excluded.explanation,
        updated_at=CURRENT_TIMESTAMP
    """
    with get_conn() as conn:
        before = conn.total_changes
        conn.executemany(sql, rows)
        conn.commit()
        return conn.total_changes - before


def fetch_recent_trades(limit: int = 500) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            ORDER BY filing_date DESC, trade_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_top_scores(limit: int = 50) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM scores
            ORDER BY opportunity_score DESC, consensus_score DESC, whale_score DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
