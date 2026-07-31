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
from app.collectors.sec_13f import collect_institutional_13f_holdings, get_institutional_13f_status
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
from app.domain.trade_classification import is_primary_transaction, primary_transactions
from app.llm.gemini_analyzer import analyze_with_gemini
from app.intelligence import build_rankings, load_wis_config, normalize_trades, score_signals
from app.reports.html_report import build_html_report, save_report
from app.reports.mailer import send_report
from app.reports.v40_report import apply_v40_report_layout

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


def _is_inserted_in_run(row: dict, run_started_at: str) -> bool:
    created_at = str(row.get("created_at") or "")[:19]
    return bool(created_at and created_at >= run_started_at[:19])


def run_scan() -> dict:
    init_db()
    baseline_trade_count = _count_existing_trades_before_run()
    log.info("Existing disclosures before collection: %s", baseline_trade_count)
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
        log.info("Collected OGE executive disclosures: %s", len(oge_trades))
        institutional_13f_rows = collect_institutional_13f_holdings(settings.sec_user_agent, settings.lookback_days)
        log.info("Collected institutional 13F holdings: %s", len(institutional_13f_rows))
        disclosures = sec_trades + congress_trades + oge_trades + institutional_13f_rows
        log.info("Collected normalized disclosures: %s", len(disclosures))

        new_disclosure_count = upsert_trades(disclosures)
        log.info("Inserted new disclosures: %s", new_disclosure_count)
        repaired_13f_count = normalize_institutional_13f_amounts()
        if repaired_13f_count:
            log.info("Repaired persisted institutional 13F amount rows: %s", repaired_13f_count)

        # V40: keep all disclosures in storage and dedicated report sections, but
        # only genuine BUY/SELL/EXCHANGE rows may enter transaction scoring,
        # consensus, BUY/SELL rankings, and transaction counts.
        all_window_rows = [_row_to_dict(r) for r in fetch_trades_since(settings.scan_start_date, limit=50000)]
        if not all_window_rows:
            all_window_rows = [
                t for t in disclosures
                if str(t.get("trade_date") or t.get("filing_date") or "")[:10] >= settings.scan_start_date
            ]
        scoring_base = primary_transactions(all_window_rows)
        new_primary_trade_count = sum(
            1 for row in all_window_rows
            if is_primary_transaction(row) and _is_inserted_in_run(row, run_started_at)
        )
        log.info(
            "V40 classification: report_disclosures=%s primary_transactions=%s new_primary_transactions=%s",
            len(all_window_rows),
            len(scoring_base),
            new_primary_trade_count,
        )

        consensus_rows = build_consensus_scores(scoring_base)
        scored = score_opportunities(consensus_rows)

        # V39.0 unified Whale Intelligence Score (WIS). Transaction-based inputs
        # use only genuine transactions. Historical 13F rows are merged separately
        # because the institutional pillar requires adjacent reporting periods.
        wis_config = load_wis_config()
        wis_13f_history = [_row_to_dict(r) for r in fetch_institutional_13f_holdings("1900-01-01", limit=20000)]
        wis_input_by_source_id = {str(r.get("source_id") or f"row:{i}"): r for i, r in enumerate(scoring_base)}
        for i, row in enumerate(wis_13f_history):
            wis_input_by_source_id.setdefault(str(row.get("source_id") or f"13f:{i}"), row)
        wis_signals = normalize_trades(wis_input_by_source_id.values())
        wis_scores = score_signals(wis_signals, wis_config)
        wis_rankings = build_rankings(wis_scores, wis_config.top_n)
        log.info("WIS generated: signals=%s tickers=%s", len(wis_signals), len(wis_scores))

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
        recent_disclosures = [_row_to_dict(r) for r in fetch_trades_since(settings.scan_start_date, limit=1000)]
        recent_trades = primary_transactions(recent_disclosures)
        political_recent_trades = primary_transactions([_row_to_dict(r) for r in fetch_recent_political_trades(limit=300)])
        political_summary = [_row_to_dict(r) for r in fetch_political_action_summary()]
        market_context = [_row_to_dict(r) for r in fetch_market_snapshots(limit=50)]
        trump_oge_trades = [_row_to_dict(r) for r in fetch_trump_oge_trades(limit=500)]
        oge_executive_trades = [_row_to_dict(r) for r in fetch_oge_executive_trades(limit=800)]
        oge_summary = [_row_to_dict(r) for r in fetch_oge_action_summary()]
        institutional_13f_holdings = [_row_to_dict(r) for r in fetch_institutional_13f_holdings("1900-01-01", limit=5000)]
        institutional_13f_status = get_institutional_13f_status()

        buy_signal_tickers = [str(r.get("ticker") or "") for r in top_scores if float(r.get("buy_amount") or 0) > 0]
        sell_signal_tickers = sorted({
            str(r.get("ticker") or "")
            for r in top_scores
            if float(r.get("sell_amount") or 0) > 0
            and (str(r.get("signal_label", "")).startswith("减持") or float(r.get("buy_amount") or 0) > 0)
        })
        buy_evidence = primary_transactions([_row_to_dict(r) for r in fetch_trade_evidence_for_tickers(buy_signal_tickers, "BUY", settings.lookback_days, limit=160)])
        sell_evidence = primary_transactions([_row_to_dict(r) for r in fetch_trade_evidence_for_tickers(sell_signal_tickers, "SELL", settings.lookback_days, limit=5000)])
        core_buy_trades = primary_transactions([_row_to_dict(r) for r in fetch_core_trades_by_action("BUY", settings.lookback_days, limit=120)])
        core_sell_trades = primary_transactions([_row_to_dict(r) for r in fetch_core_trades_by_action("SELL", settings.lookback_days, limit=1000)])
        noncore_trades = primary_transactions([_row_to_dict(r) for r in fetch_noncore_recent_trades(settings.lookback_days, limit=100)])

        seen_source_ids = {str(t.get("source_id") or "") for t in recent_trades}
        for t in political_recent_trades:
            sid = str(t.get("source_id") or "")
            if sid and sid not in seen_source_ids:
                recent_trades.append(t)
                seen_source_ids.add(sid)
        log.info("Recent transaction rows: total=%s political=%s buy_evidence=%s sell_evidence=%s noncore=%s political_summary=%s", len(recent_trades), len(political_recent_trades), len(buy_evidence), len(sell_evidence), len(noncore_trades), political_summary)

        ai_recent_context = core_buy_trades[:40] + core_sell_trades[:40] + political_recent_trades[:40] + primary_transactions(trump_oge_trades)[:40]
        ai_analysis = analyze_with_gemini(top_scores, ai_recent_context)
        html = build_html_report(
            top_scores,
            recent_trades,
            ai_analysis,
            new_trade_count=new_primary_trade_count,
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
            institutional_13f_status=institutional_13f_status,
            new_since=run_started_at if baseline_trade_count > 0 else None,
            baseline_trade_count=baseline_trade_count,
            wis_rankings=wis_rankings,
        )
        html = apply_v40_report_layout(
            html,
            recent_trades,
            new_since=run_started_at if baseline_trade_count > 0 else None,
        )
        path = save_report(html)
        report_path = str(path)
        log.info("Report saved: %s", report_path)

        if settings.send_email:
            daily_status = "新增" if new_primary_trade_count > 0 else "无新增"
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

        notes = f"new_disclosures={new_disclosure_count}; new_primary_transactions={new_primary_trade_count}"
        _finish_run(run_id, "SUCCESS", new_primary_trade_count, report_path, notes)
        return {
            "status": "SUCCESS",
            "new_trade_count": new_primary_trade_count,
            "new_disclosure_count": new_disclosure_count,
            "report_path": report_path,
        }
    except Exception as exc:  # noqa: BLE001
        log.exception("Scan failed")
        _finish_run(run_id, "FAILED", 0, report_path, str(exc))
        raise


if __name__ == "__main__":
    result = run_scan()
    print(result)
