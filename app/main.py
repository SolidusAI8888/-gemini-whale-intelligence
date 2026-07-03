from __future__ import annotations

from datetime import datetime
import logging
import sys
from typing import Any

from app.analyzers.consensus import build_consensus_scores
from app.analyzers.opportunity import score_opportunities
from app.collectors.congress import collect_congress_trades
from app.collectors.sec_client import SecClient
from app.collectors.sec_form4 import collect_sec_form4_trades
from app.collectors.market_data import apply_market_context_to_scores, collect_market_snapshots
from app.collectors.sec_13f import collect_institutional_13f_holdings
from app.collectors.oge_executive import collect_oge_executive_trades
from app.collectors.universe import build_company_universe, tickers_from_companies
from app.config import settings
from app.db import (
    fetch_political_action_summary,
    fetch_recent_political_trades,
    fetch_recent_trades,
    fetch_top_scores,
    fetch_trades_since,
    fetch_market_snapshots,
    fetch_oge_action_summary,
    fetch_oge_executive_trades,
    fetch_institutional_13f_holdings,
    fetch_trump_oge_trades,
    fetch_core_trades_by_action,
    fetch_noncore_recent_trades,
    fetch_trade_evidence_for_tickers,
    get_conn,
    init_db,
    insert_scores,
    upsert_market_snapshots,
    upsert_trades,
    normalize_institutional_13f_amounts,
)
from app.llm.gemini_analyzer import analyze_with_gemini
from app.reports.html_report import build_html_report, save_report
from app.reports.mailer import send_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("whale_gemini")


def _row_to_dict(row: Any) -> dict:
    if hasattr(row, "keys"):
        return {key: row[key] for key in row.keys()}
    return dict(row)


def _start_run() -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO runs(status, notes) VALUES (?, ?)", ("RUNNING", ""))
        conn.commit()
        return int(cur.lastrowid)


def _finish_run(run_id: int, status: str, new_trade_count: int, report_path: str | None, notes: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE runs
            SET finished_at=CURRENT_TIMESTAMP, status=?, new_trade_count=?, report_path=?, notes=?
            WHERE id=?
            """,
            (status, new_trade_count, report_path, notes, run_id),
        )
        conn.commit()


def _count_existing_trades_before_run() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM trades").fetchone()
        return int(row["n"] if row else 0)


def run_scan() -> dict:
    init_db()
    baseline_trade_count = _count_existing_trades_before_run()
    log.info("Existing trades before collection: %s", baseline_trade_count)
    run_id = _start_run()
    # UTC timestamp used by the report to mark rows inserted in this run.
    # With V22's persisted DB cache, this is a real day-over-day comparison.
    run_started_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    report_path = None
    try:
        log.info("Gemini Whale scan started")
        log.info("Settings: lookback_days=%s max_companies=%s min_opportunity_score=%s dry_run=%s enable_gemini=%s enable_political=%s political_provider=%s political_scope=%s fmp_key_present=%s enable_market_data=%s alpha_key_present=%s finnhub_key_present=%s enable_oge=%s", settings.lookback_days, settings.max_companies, settings.min_opportunity_score, settings.dry_run, settings.enable_gemini, settings.enable_political_trades, settings.political_provider, settings.political_universe_scope, bool(settings.fmp_api_key), settings.enable_market_data, bool(settings.alpha_vantage_api_key), bool(settings.finnhub_api_key), settings.enable_oge_executive_trades)

        companies = build_company_universe(settings.sec_user_agent, settings.max_companies)
        log.info("Company universe size after filters: %s", len(companies))
        sec_client = SecClient(settings.sec_user_agent)

        sec_trades = collect_sec_form4_trades(companies, sec_client, settings.lookback_days)
        target_tickers = tickers_from_companies(companies)
        political_scope = settings.political_universe_scope
        political_target_tickers = target_tickers if political_scope == "core" else set()
        congress_trades = collect_congress_trades(political_target_tickers, settings.sec_user_agent, settings.lookback_days)
        log.info("Collected political trades: %s", len(congress_trades))
        oge_trades = collect_oge_executive_trades(settings.sec_user_agent, settings.lookback_days)
        log.info("Collected OGE executive trades: %s", len(oge_trades))
        institutional_13f_rows = collect_institutional_13f_holdings(settings.sec_user_agent, settings.lookback_days)
        log.info("Collected institutional 13F holdings: %s", len(institutional_13f_rows))
        trades = sec_trades + congress_trades + oge_trades + institutional_13f_rows
        log.info("Collected normalized trades: %s", len(trades))

        new_count = upsert_trades(trades)
        log.info("Inserted new trades: %s", new_count)
        repaired_13f_count = normalize_institutional_13f_amounts()
        if repaired_13f_count:
            log.info("Repaired persisted institutional 13F amount rows: %s", repaired_13f_count)

        # V18 formal report/scoring window starts at SCAN_START_DATE (default 2026-01-01).
        # Use the DB window after inserting fresh rows, so daily reports reflect the
        # full 2026-to-date activity instead of only the current collector lookback.
        scoring_base = [_row_to_dict(r) for r in fetch_trades_since(settings.scan_start_date, limit=50000)]
        if not scoring_base:
            scoring_base = [t for t in trades if str(t.get("trade_date") or t.get("filing_date") or "")[:10] >= settings.scan_start_date]
        consensus_rows = build_consensus_scores(scoring_base)
        scored = score_opportunities(consensus_rows)
        # Pull market/valuation/sentiment context for the highest-interest tickers,
        # then apply a small, transparent adjustment to opportunity scores.
        candidate_symbols = [row["ticker"] for row in sorted(scored, key=lambda r: r.get("opportunity_score", 0), reverse=True)]
        market_snapshots = collect_market_snapshots(candidate_symbols)
        market_new_count = upsert_market_snapshots(market_snapshots)
        log.info("Market snapshots upserted: %s", market_new_count)
        scored = apply_market_context_to_scores(scored, market_snapshots)

        pre_filter_count = len(scored)
        scored = [row for row in scored if row["opportunity_score"] >= settings.min_opportunity_score]
        log.info("Opportunity scores: before_filter=%s after_filter=%s min_score=%s", pre_filter_count, len(scored), settings.min_opportunity_score)
        insert_scores(scored)

        top_scores = scored if scored else [_row_to_dict(r) for r in fetch_top_scores(limit=50)]
        recent_trades = [_row_to_dict(r) for r in fetch_trades_since(settings.scan_start_date, limit=1000)]
        political_recent_trades = [_row_to_dict(r) for r in fetch_recent_political_trades(limit=300)]
        political_summary = [_row_to_dict(r) for r in fetch_political_action_summary()]
        market_context = [_row_to_dict(r) for r in fetch_market_snapshots(limit=50)]
        trump_oge_trades = [_row_to_dict(r) for r in fetch_trump_oge_trades(limit=500)]
        oge_executive_trades = [_row_to_dict(r) for r in fetch_oge_executive_trades(limit=800)]
        oge_summary = [_row_to_dict(r) for r in fetch_oge_action_summary()]
        institutional_13f_holdings = [_row_to_dict(r) for r in fetch_institutional_13f_holdings(settings.scan_start_date, limit=500)]

        buy_signal_tickers = [str(r.get("ticker") or "") for r in top_scores if float(r.get("buy_amount") or 0) > 0]
        # Include BUY-radar tickers in SELL evidence so related SELL rows (for
        # example TSLA) remain auditable even when they do not make the global
        # sell Top N by amount/opportunity score.
        sell_signal_tickers = sorted({
            str(r.get("ticker") or "")
            for r in top_scores
            if float(r.get("sell_amount") or 0) > 0
            and (str(r.get("signal_label", "")).startswith("减持") or float(r.get("buy_amount") or 0) > 0)
        })
        buy_evidence = [_row_to_dict(r) for r in fetch_trade_evidence_for_tickers(buy_signal_tickers, "BUY", settings.lookback_days, limit=160)]
        sell_evidence = [_row_to_dict(r) for r in fetch_trade_evidence_for_tickers(sell_signal_tickers, "SELL", settings.lookback_days, limit=5000)]
        core_buy_trades = [_row_to_dict(r) for r in fetch_core_trades_by_action("BUY", settings.lookback_days, limit=120)]
        core_sell_trades = [_row_to_dict(r) for r in fetch_core_trades_by_action("SELL", settings.lookback_days, limit=1000)]
        noncore_trades = [_row_to_dict(r) for r in fetch_noncore_recent_trades(settings.lookback_days, limit=100)]

        # Ensure political trades are visible even when recent SEC Form 4 rows dominate
        # the generic recent-trades query.
        seen_source_ids = {str(t.get("source_id") or "") for t in recent_trades}
        for t in political_recent_trades:
            sid = str(t.get("source_id") or "")
            if sid and sid not in seen_source_ids:
                recent_trades.append(t)
                seen_source_ids.add(sid)
        log.info("Recent report rows: total=%s political=%s buy_evidence=%s sell_evidence=%s noncore=%s political_summary=%s", len(recent_trades), len(political_recent_trades), len(buy_evidence), len(sell_evidence), len(noncore_trades), political_summary)

        ai_recent_context = (core_buy_trades[:40] + core_sell_trades[:40] + political_recent_trades[:40] + trump_oge_trades[:40])
        ai_analysis = analyze_with_gemini(top_scores, ai_recent_context)
        html = build_html_report(
            top_scores,
            recent_trades,
            ai_analysis,
            new_trade_count=new_count,
            political_summary=political_summary,
            market_context=market_context,
            buy_evidence=buy_evidence,
            sell_evidence=sell_evidence,
            core_buy_trades=core_buy_trades,
            core_sell_trades=core_sell_trades,
            noncore_trades=noncore_trades,
            trump_oge_trades=trump_oge_trades,
            oge_executive_trades=oge_executive_trades,
            oge_summary=oge_summary,
            institutional_13f_holdings=institutional_13f_holdings,
            new_since=run_started_at if baseline_trade_count > 0 else None,
            baseline_trade_count=baseline_trade_count,
        )
        path = save_report(html)
        report_path = str(path)
        log.info("Report saved: %s", report_path)

        if settings.send_email:
            daily_status = "新增" if new_count > 0 else "无新增"
            subject = f"Gemini-美股聪明钱_政商巨鲸行动追踪 {datetime.now().strftime('%Y-%m-%d')}（{daily_status}）"
            sent = send_report(subject, html)
            if sent:
                marker = settings.report_dir.parent / "email_sent.flag"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(datetime.utcnow().isoformat(timespec="seconds"), encoding="utf-8")
                log.info("Email sent marker written: %s", marker)
            else:
                log.warning("send_report returned False; scheduled workflow backup delivery may try SMTP if configured")
        else:
            log.info("SEND_EMAIL=false; email not sent")

        _finish_run(run_id, "SUCCESS", new_count, report_path)
        return {"status": "SUCCESS", "new_trade_count": new_count, "report_path": report_path}
    except Exception as exc:  # noqa: BLE001
        log.exception("Scan failed")
        _finish_run(run_id, "FAILED", 0, report_path, str(exc))
        raise


if __name__ == "__main__":
    result = run_scan()
    print(result)
