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
from app.collectors.universe import build_company_universe, tickers_from_companies
from app.config import settings
from app.db import fetch_recent_trades, fetch_top_scores, get_conn, init_db, insert_scores, upsert_trades
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


def run_scan() -> dict:
    init_db()
    run_id = _start_run()
    report_path = None
    try:
        log.info("Gemini Whale scan started")
        log.info("Settings: lookback_days=%s max_companies=%s min_opportunity_score=%s dry_run=%s enable_gemini=%s", settings.lookback_days, settings.max_companies, settings.min_opportunity_score, settings.dry_run, settings.enable_gemini)

        companies = build_company_universe(settings.sec_user_agent, settings.max_companies)
        log.info("Company universe size after filters: %s", len(companies))
        sec_client = SecClient(settings.sec_user_agent)

        sec_trades = collect_sec_form4_trades(companies, sec_client, settings.lookback_days)
        target_tickers = tickers_from_companies(companies)
        congress_trades = collect_congress_trades(target_tickers, settings.sec_user_agent, settings.lookback_days)
        log.info("Collected political trades: %s", len(congress_trades))
        trades = sec_trades + congress_trades
        log.info("Collected normalized trades: %s", len(trades))

        new_count = upsert_trades(trades)
        log.info("Inserted new trades: %s", new_count)

        # Use the freshly collected rows for scoring; if none collected, use recent DB records to keep report informative.
        scoring_base = trades if trades else [_row_to_dict(r) for r in fetch_recent_trades(limit=500)]
        consensus_rows = build_consensus_scores(scoring_base)
        scored = score_opportunities(consensus_rows)
        pre_filter_count = len(scored)
        scored = [row for row in scored if row["opportunity_score"] >= settings.min_opportunity_score]
        log.info("Opportunity scores: before_filter=%s after_filter=%s min_score=%s", pre_filter_count, len(scored), settings.min_opportunity_score)
        insert_scores(scored)

        top_scores = scored if scored else [_row_to_dict(r) for r in fetch_top_scores(limit=50)]
        recent_trades = [_row_to_dict(r) for r in fetch_recent_trades(limit=200)]

        ai_analysis = analyze_with_gemini(top_scores, recent_trades)
        html = build_html_report(top_scores, recent_trades, ai_analysis, new_trade_count=new_count)
        path = save_report(html)
        report_path = str(path)
        log.info("Report saved: %s", report_path)

        if new_count > 0 or not settings.dry_run:
            subject = f"Gemini-美股聪明钱_政商巨鲸行动追踪 {datetime.now().strftime('%Y-%m-%d')}"
            send_report(subject, html)
        else:
            log.info("No new trades and DRY_RUN=true; email not sent")

        _finish_run(run_id, "SUCCESS", new_count, report_path)
        return {"status": "SUCCESS", "new_trade_count": new_count, "report_path": report_path}
    except Exception as exc:  # noqa: BLE001
        log.exception("Scan failed")
        _finish_run(run_id, "FAILED", 0, report_path, str(exc))
        raise


if __name__ == "__main__":
    result = run_scan()
    print(result)
