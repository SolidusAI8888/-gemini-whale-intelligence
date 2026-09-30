from __future__ import annotations

import inspect

import pytest

from app import main
from app.domain.asset_quality import normalize_oge_asset
from app.domain.trade_classification import primary_transactions
from app.reports.quality_gate import ReportQualityError, validate_key_political_visibility
from app.reports.v40_report import build_active_buy_radar


def _political_buy(ticker: str, *, amount: float = 750_000, actor: str = "Nancy Pelosi") -> dict:
    return {
        "ticker": ticker,
        "action": "BUY",
        "transaction_code": "P",
        "trade_date": "2026-05-29",
        "filing_date": "2026-06-01",
        "source_id": f"political-{ticker.lower()}-large-buy",
        "source": "POLITICAL_HOUSE",
        "whale_category": "Political:House",
        "amount_usd": amount,
        "shares": 0,
        "price": 0,
        "whale_name": actor,
        "raw_json": {
            "asset_type": "Option",
            "option_type": "Call",
            "description": f"Purchased call options in {ticker}",
        },
    }


def _small_buy(index: int) -> dict:
    # Many records deliberately precede the historical key rows.  They model the
    # real production database where Form4/Congress volume exceeded the old
    # 1000/300 report re-fetch caps.
    return {
        "ticker": f"T{index % 100:03d}",
        "action": "BUY",
        "transaction_code": "P",
        "trade_date": "2026-07-30",
        "filing_date": "2026-07-31",
        "source_id": f"small-{index}",
        "source": "POLITICAL_HOUSE",
        "whale_category": "Political:House",
        "amount_usd": 1_000,
        "shares": 0,
        "price": 0,
        "whale_name": f"Member {index}",
        "raw_json": {},
    }


def test_v46_full_report_window_keeps_large_uber_msft_intc_after_1300_rows():
    rows = [_small_buy(i) for i in range(1300)]
    rows.extend([
        _political_buy("UBER"),
        _political_buy("MSFT"),
        _political_buy("INTC"),
    ])

    formal_primary = primary_transactions(rows)
    html = build_active_buy_radar(formal_primary)

    assert "<b>UBER</b>" in html
    assert "<b>MSFT</b>" in html
    assert "<b>INTC</b>" in html
    assert "$750.0K" in html
    validate_key_political_visibility(html, formal_primary)


def test_v46_release_gate_fails_if_database_signal_vanishes_from_final_html():
    rows = [_political_buy("UBER")]
    html = build_active_buy_radar(rows)
    broken = html.replace("<b>UBER</b>", "<b>OTHER</b>")

    with pytest.raises(ReportQualityError, match="UBER"):
        validate_key_political_visibility(broken, rows)



def test_v53_release_gate_accepts_large_buy_visible_in_political_chapter_even_if_outside_global_top20():
    rows = [_political_buy("MSFT")]
    html = (
        '<section id="v40-active-buy-radar"><table><tr><td><b>OTHER</b></td></tr></table></section>'
        '<h2 id="political">三、政界巨鲸行动</h2>'
        '<table><tbody><tr><td><b>MSFT</b></td><td>BUY</td><td>$750.0K</td></tr></tbody></table>'
        '<h2 id="institutional">四、机构巨鲸</h2>'
    )

    validate_key_political_visibility(html, rows)


def test_v53_release_gate_still_fails_if_large_political_buy_missing_everywhere():
    rows = [_political_buy("MSFT")]
    html = (
        '<section id="v40-active-buy-radar"><table><tr><td><b>OTHER</b></td></tr></table></section>'
        '<h2 id="political">三、政界巨鲸行动</h2><p>暂无相关记录。</p>'
        '<h2 id="institutional">四、机构巨鲸</h2>'
    )

    with pytest.raises(ReportQualityError, match="MSFT"):
        validate_key_political_visibility(html, rows)

def test_v46_run_scan_does_not_restore_old_truncated_report_refetches():
    source = inspect.getsource(main.run_scan)

    assert "fetch_trades_since(settings.scan_start_date, limit=1000)" not in source
    assert "fetch_recent_political_trades(limit=300)" not in source
    assert "recent_trades = list(scoring_base)" in source
    assert "validate_key_political_visibility(html, recent_trades)" in source


def test_v46_oge_amount_qualifier_fragment_is_not_an_asset():
    for raw in ["(or less", "(or less)", "or less", "N/A (or less)"]:
        normalized = normalize_oge_asset(raw)
        assert normalized.quality == "rejected"
