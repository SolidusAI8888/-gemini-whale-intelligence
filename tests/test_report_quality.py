from app.reports.html_report import build_html_report


def test_report_is_compact_daily_brief_and_splits_business_political():
    html = build_html_report(
        top_scores=[],
        recent_trades=[
            {"ticker":"BUYME","action":"BUY","transaction_code":"P","whale_name":"CEO A","source":"SEC_FORM4","trade_date":"2026-02-01","amount_usd":1000000},
            {"ticker":"POLI","action":"SELL","transaction_code":"S","whale_name":"Nancy Pelosi","source":"POLITICAL_HOUSE","trade_date":"2026-03-01","amount_usd":500000},
            {"ticker":"OLD","action":"BUY","transaction_code":"P","whale_name":"Old","source":"SEC_FORM4","trade_date":"2025-12-01","amount_usd":999999999},
        ],
        ai_analysis="ok",
        new_trade_count=1,
    )
    assert "今日结论总览" in html
    assert "商界巨鲸行动" in html
    assert "政界巨鲸行动" in html
    assert "主动买入股票关联 SELL 审计" not in html
    assert "行情 / 基本面 / 新闻情绪补充" not in html
    assert "OLD" not in html
    assert "BUYME" in html
    assert "POLI" in html


def test_trump_and_pelosi_highlight_does_not_rewrite_css_selector():
    html = build_html_report(
        top_scores=[],
        recent_trades=[
            {"ticker":"AVGO","action":"BUY","transaction_code":"P","whale_name":"Donald J. Trump","source":"OGE_EXECUTIVE_TRUMP","trade_date":"2026-02-10","amount_usd":3000000},
            {"ticker":"INTC","action":"BUY","transaction_code":"P","whale_name":"Nancy Pelosi","source":"POLITICAL_HOUSE","trade_date":"2026-05-29","amount_usd":3000000},
        ],
        ai_analysis="Donald J. Trump and Nancy Pelosi mention",
        new_trade_count=1,
    )
    assert ".trump-highlight" in html
    assert ".pelosi-highlight" in html
    assert ".<span" not in html
    assert '<span class="trump-highlight">Donald J. Trump</span>' in html
    assert '<span class="pelosi-highlight">Nancy Pelosi</span>' in html


def test_new_rows_are_orange_and_oge_assets_excluded_from_political_details():
    html = build_html_report(
        top_scores=[],
        recent_trades=[
            {"ticker":"INTC","action":"BUY","transaction_code":"P","whale_name":"Nancy Pelosi","source":"POLITICAL_HOUSE","trade_date":"2026-05-29","filing_date":"2026-06-23","amount_usd":3000000,"created_at":"2026-07-01 00:00:01"},
            {"ticker":"BTC","action":"HOLDING","transaction_code":"278e","whale_name":"JD Vance","source":"OGE_EXECUTIVE_ASSET","trade_date":"2027-08-31","filing_date":"2026-07-01","amount_usd":100000,"created_at":"2026-07-01 00:00:01","raw_json":"{\"report_type\":\"OGE_278e\",\"asset_name\":\"Bitcoin\"}"},
        ],
        oge_executive_trades=[
            {"ticker":"BTC","action":"HOLDING","transaction_code":"278e","whale_name":"JD Vance","source":"OGE_EXECUTIVE_ASSET","trade_date":"2027-08-31","filing_date":"2026-07-01","amount_usd":100000,"created_at":"2026-07-01 00:00:01","raw_json":"{\"report_type\":\"OGE_278e\",\"asset_name\":\"Bitcoin\"}"},
        ],
        new_trade_count=2,
        new_since="2026-07-01 00:00:00",
        baseline_trade_count=100,
    )
    assert "今日新增内容总览" in html
    assert "row-new" in html
    assert ".change-new" in html
    assert "JD Vance" in html
    assert "行政分支关键人物投资标的雷达" in html
    # OGE asset future/report-period dates should not appear as political transaction dates.
    assert "2027-08-31" not in html
    assert "不适用" not in html  # hidden from political details; asset table uses filing/report date


def test_institutional_13f_report_section_uses_report_period_not_trade_language():
    html = build_html_report(
        top_scores=[],
        recent_trades=[],
        institutional_13f_holdings=[
            {"ticker":"UBER","action":"HOLDING_13F","transaction_code":"13F","whale_name":"Bill Ackman","insider_role":"Pershing Square Capital Management","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":2150000000,"shares":30000000,"created_at":"2026-07-01 00:00:01","raw_json":"{\"manager\":\"Pershing Square Capital Management\",\"lead_investor\":\"Bill Ackman\",\"nameOfIssuer\":\"UBER TECHNOLOGIES INC\",\"report_period\":\"2026-03-31\"}"},
        ],
        new_trade_count=1,
        new_since="2026-07-01 00:00:00",
        baseline_trade_count=100,
    )
    assert "机构巨鲸 13F 持仓雷达" in html
    assert "Pershing Square Capital Management" in html
    assert "UBER" in html
    assert "季度持仓披露" in html or "季度持仓" in html
