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


def fetch_recent_political_trades(limit: int = 200) -> list[sqlite3.Row]:
    """Return recent political trades separately from the general recent list.

    The general recent table can be dominated by SEC Form 4 rows, which caused
    POLITICAL_HOUSE records to be collected and inserted but not shown in the
    report.  Match both source and whale_category to be robust across providers.
    """
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            WHERE (source LIKE 'POLITICAL%' OR whale_category LIKE 'Political%')
              AND action IN ('BUY', 'SELL')
            ORDER BY filing_date DESC, trade_date DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_political_action_summary() -> list[sqlite3.Row]:
    """Summarize political records so the report can diagnose empty displays."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                action,
                COUNT(*) AS record_count,
                COUNT(DISTINCT ticker) AS ticker_count,
                ROUND(SUM(COALESCE(amount_usd, 0)), 2) AS total_amount_usd
            FROM trades
            WHERE source LIKE 'POLITICAL%' OR whale_category LIKE 'Political%'
            GROUP BY action
            ORDER BY record_count DESC, action ASC
            """
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


def upsert_market_snapshots(rows: Iterable[Mapping[str, Any]]) -> int:
    data = list(rows)
    if not data:
        return 0
    sql = """
    INSERT INTO market_snapshots (
        ticker, price, change_pct, volume, ret_20d, ret_60d, sma20, sma50,
        week_52_high, week_52_low, pe_ratio, ps_ratio, peg_ratio,
        revenue_growth_yoy, profit_margin, gross_margin, net_margin, market_cap, beta,
        news_buzz, news_sentiment_score, news_bearish_percent,
        finnhub_insider_buy_count, finnhub_insider_sell_count,
        finnhub_insider_buy_amount, finnhub_insider_sell_amount,
        trend_score, valuation_score, sentiment_score, data_sources, summary_note, updated_at
    ) VALUES (
        :ticker, :price, :change_pct, :volume, :ret_20d, :ret_60d, :sma20, :sma50,
        :week_52_high, :week_52_low, :pe_ratio, :ps_ratio, :peg_ratio,
        :revenue_growth_yoy, :profit_margin, :gross_margin, :net_margin, :market_cap, :beta,
        :news_buzz, :news_sentiment_score, :news_bearish_percent,
        :finnhub_insider_buy_count, :finnhub_insider_sell_count,
        :finnhub_insider_buy_amount, :finnhub_insider_sell_amount,
        :trend_score, :valuation_score, :sentiment_score, :data_sources, :summary_note, CURRENT_TIMESTAMP
    )
    ON CONFLICT(ticker) DO UPDATE SET
        price=excluded.price,
        change_pct=excluded.change_pct,
        volume=excluded.volume,
        ret_20d=excluded.ret_20d,
        ret_60d=excluded.ret_60d,
        sma20=excluded.sma20,
        sma50=excluded.sma50,
        week_52_high=excluded.week_52_high,
        week_52_low=excluded.week_52_low,
        pe_ratio=excluded.pe_ratio,
        ps_ratio=excluded.ps_ratio,
        peg_ratio=excluded.peg_ratio,
        revenue_growth_yoy=excluded.revenue_growth_yoy,
        profit_margin=excluded.profit_margin,
        gross_margin=excluded.gross_margin,
        net_margin=excluded.net_margin,
        market_cap=excluded.market_cap,
        beta=excluded.beta,
        news_buzz=excluded.news_buzz,
        news_sentiment_score=excluded.news_sentiment_score,
        news_bearish_percent=excluded.news_bearish_percent,
        finnhub_insider_buy_count=excluded.finnhub_insider_buy_count,
        finnhub_insider_sell_count=excluded.finnhub_insider_sell_count,
        finnhub_insider_buy_amount=excluded.finnhub_insider_buy_amount,
        finnhub_insider_sell_amount=excluded.finnhub_insider_sell_amount,
        trend_score=excluded.trend_score,
        valuation_score=excluded.valuation_score,
        sentiment_score=excluded.sentiment_score,
        data_sources=excluded.data_sources,
        summary_note=excluded.summary_note,
        updated_at=CURRENT_TIMESTAMP
    """
    with get_conn() as conn:
        before = conn.total_changes
        conn.executemany(sql, data)
        conn.commit()
        return conn.total_changes - before


def fetch_market_snapshots(limit: int = 100) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM market_snapshots
            ORDER BY updated_at DESC, ticker ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_oge_executive_trades(limit: int = 500) -> list[sqlite3.Row]:
    """Return OGE executive branch trades, including Trump and cabinet officials."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            WHERE source LIKE 'OGE_EXECUTIVE%' OR whale_category LIKE 'Executive:%'
            ORDER BY filing_date DESC, trade_date DESC, COALESCE(amount_usd, 0) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_trump_oge_trades(limit: int = 500) -> list[sqlite3.Row]:
    """Return Trump OGE trades for the dedicated President section."""
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            WHERE source = 'OGE_EXECUTIVE_TRUMP'
               OR (whale_category LIKE 'Executive:%' AND whale_name LIKE '%Trump%')
            ORDER BY filing_date DESC, trade_date DESC, COALESCE(amount_usd, 0) DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_oge_action_summary() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                whale_name,
                insider_role,
                action,
                COUNT(*) AS record_count,
                COUNT(DISTINCT ticker) AS ticker_count,
                ROUND(SUM(COALESCE(amount_usd, 0)), 2) AS total_amount_usd
            FROM trades
            WHERE source LIKE 'OGE_EXECUTIVE%' OR whale_category LIKE 'Executive:%'
            GROUP BY whale_name, insider_role, action
            ORDER BY whale_name ASC, action ASC
            """
        ).fetchall()


def fetch_market_snapshots_for_tickers(tickers: Iterable[str]) -> list[sqlite3.Row]:
    symbols = [str(t).upper().strip() for t in tickers if str(t).strip()]
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    with get_conn() as conn:
        return conn.execute(
            f"SELECT * FROM market_snapshots WHERE ticker IN ({placeholders}) ORDER BY ticker ASC",
            symbols,
        ).fetchall()

from datetime import date, timedelta


def _cutoff_date(days: int) -> str:
    try:
        d = int(days)
    except Exception:
        d = 365
    return (date.today() - timedelta(days=max(d, 1))).isoformat()


def fetch_core_trades_by_action(action: str, lookback_days: int = 365, limit: int = 120) -> list[sqlite3.Row]:
    """Fetch core open-market/private BUY or SELL rows by disclosed amount.

    This is intentionally separate from the generic recent list so large recent
    SELL rows do not hide BUY rows.  It excludes political records because those
    have their own report section.
    """
    action = str(action or "").upper()
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            WHERE action = ?
              AND NOT (source LIKE 'POLITICAL%' OR whale_category LIKE 'Political%')
              AND COALESCE(filing_date, '') >= ?
            ORDER BY COALESCE(amount_usd, 0) DESC, filing_date DESC, trade_date DESC, id DESC
            LIMIT ?
            """,
            (action, _cutoff_date(lookback_days), limit),
        ).fetchall()


def fetch_noncore_recent_trades(lookback_days: int = 365, limit: int = 80) -> list[sqlite3.Row]:
    """Fetch non-core SEC rows (option exercise, grant, tax, gift, etc.).

    These rows are useful for explaining why a news headline may say an insider
    'acquired' shares even though the BUY table correctly excludes the row from
    active P/BUY signals.
    """
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT * FROM trades
            WHERE action NOT IN ('BUY', 'SELL')
              AND NOT (source LIKE 'POLITICAL%' OR whale_category LIKE 'Political%')
              AND COALESCE(filing_date, '') >= ?
            ORDER BY COALESCE(amount_usd, 0) DESC, filing_date DESC, trade_date DESC, id DESC
            LIMIT ?
            """,
            (_cutoff_date(lookback_days), limit),
        ).fetchall()


def fetch_trade_evidence_for_tickers(tickers: Iterable[str], action: str, lookback_days: int = 365, limit: int = 80) -> list[sqlite3.Row]:
    """Fetch largest trades supporting top BUY/SELL signals."""
    symbols = sorted({str(t).upper().strip() for t in tickers if str(t).strip()})
    if not symbols:
        return []
    placeholders = ",".join("?" for _ in symbols)
    params = [str(action).upper(), _cutoff_date(lookback_days), *symbols, int(limit)]
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT * FROM trades
            WHERE action = ?
              AND COALESCE(filing_date, '') >= ?
              AND ticker IN ({placeholders})
            ORDER BY COALESCE(amount_usd, 0) DESC, filing_date DESC, trade_date DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
