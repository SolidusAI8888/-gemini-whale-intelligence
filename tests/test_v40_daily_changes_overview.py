from app.reports.v40_overview import build_daily_changes_overview


def test_overview_shows_only_new_rows_and_marks_them_orange():
    rows = [
        {
            "source": "POLITICAL_HOUSE",
            "action": "BUY",
            "ticker": "NVDA",
            "whale_name": "Example Member",
            "amount_usd": 50000,
            "trade_date": "2026-07-31",
            "created_at": "2026-08-01 08:10:00",
        },
        {
            "source": "SEC_FORM4",
            "action": "SELL",
            "ticker": "MSFT",
            "whale_name": "Existing Insider",
            "amount_usd": 100000,
            "trade_date": "2026-07-30",
            "created_at": "2026-07-31 07:00:00",
        },
    ]

    html = build_daily_changes_overview(rows, new_since="2026-08-01 08:00:00")

    assert "今日新增内容总览" in html
    assert "NVDA" in html
    assert "Example Member" in html
    assert "MSFT" not in html
    assert 'class="row-new"' in html


def test_overview_includes_oge_and_13f_without_forcing_tickers():
    rows = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Cabinet Official",
            "filing_date": "2026-07-31",
            "created_at": "2026-08-01 08:10:00",
            "raw_json": '{"asset_name":"Example Family Trust","amount_range_label":"$100,001-$250,000"}',
        },
        {
            "source": "INSTITUTIONAL_13F",
            "action": "HOLDING_13F",
            "ticker": "AAPL",
            "whale_name": "Example Manager",
            "amount_usd": 2000000,
            "filing_date": "2026-07-31",
            "created_at": "2026-08-01 08:11:00",
            "raw_json": '{"nameOfIssuer":"Apple Inc.","report_period":"2026-06-30"}',
        },
    ]

    html = build_daily_changes_overview(rows, new_since="2026-08-01 08:00:00")

    assert "行政分支资产披露" in html
    assert "Example Family Trust" in html
    assert "$100,001-$250,000" in html
    assert "机构13F持仓" in html
    assert "AAPL" in html
    assert "Apple Inc." in html
