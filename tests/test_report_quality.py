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


def test_detail_new_rows_are_highlighted_without_promoting_over_larger_rows():
    html = build_html_report(
        top_scores=[],
        recent_trades=[
            {"ticker":"BIG","action":"SELL","transaction_code":"S","whale_name":"Large Old","source":"SEC_FORM4","trade_date":"2026-07-01","amount_usd":100_000_000,"created_at":"2026-07-01 00:00:00"},
            {"ticker":"NEW","action":"SELL","transaction_code":"S","whale_name":"Small New","source":"SEC_FORM4","trade_date":"2026-07-02","amount_usd":1_000_000,"created_at":"2026-07-07 08:00:01"},
        ],
        new_trade_count=1,
        new_since="2026-07-07 08:00:00",
        baseline_trade_count=10,
    )
    detail_idx = html.index("商界巨鲸必要明细")
    assert html.index("BIG", detail_idx) < html.index("NEW", detail_idx)
    new_idx = html.index("NEW", detail_idx)
    assert 'class="row-new"' in html[detail_idx:new_idx]


def test_institutional_13f_consensus_analysis_detects_multi_manager_increases():
    holdings = [
        {"ticker":"UBER","action":"HOLDING_13F","whale_name":"Bill Ackman","insider_role":"Pershing Square Capital Management","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":2_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Pershing Square Capital Management\",\"lead_investor\":\"Bill Ackman\",\"nameOfIssuer\":\"UBER TECHNOLOGIES INC\",\"report_period\":\"2026-03-31\",\"value_reported\":2000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"UBER","action":"HOLDING_13F","whale_name":"Bill Ackman","insider_role":"Pershing Square Capital Management","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":1_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Pershing Square Capital Management\",\"lead_investor\":\"Bill Ackman\",\"nameOfIssuer\":\"UBER TECHNOLOGIES INC\",\"report_period\":\"2025-12-31\",\"value_reported\":1000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"UBER","action":"HOLDING_13F","whale_name":"David Tepper","insider_role":"Appaloosa LP","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":500_000_000,"shares":10,"raw_json":"{\"manager\":\"Appaloosa LP\",\"lead_investor\":\"David Tepper\",\"nameOfIssuer\":\"UBER TECHNOLOGIES INC\",\"report_period\":\"2026-03-31\",\"value_reported\":500000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"UBER","action":"HOLDING_13F","whale_name":"David Tepper","insider_role":"Appaloosa LP","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":300_000_000,"shares":10,"raw_json":"{\"manager\":\"Appaloosa LP\",\"lead_investor\":\"David Tepper\",\"nameOfIssuer\":\"UBER TECHNOLOGIES INC\",\"report_period\":\"2025-12-31\",\"value_reported\":300000,\"value_unit\":\"thousands_usd\"}"},
    ]
    html = build_html_report(top_scores=[], recent_trades=[], institutional_13f_holdings=holdings, baseline_trade_count=10)
    assert "13F 加仓 / 新建仓集中度 Top 5" in html
    assert "$1.20B" in html
    assert "Pershing Square Capital Management" in html
    assert "Appaloosa LP" in html


def test_institutional_13f_three_top5_tables_show_current_increase_decrease():
    holdings = [
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":5_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2026-03-31\",\"value_reported\":5000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":2_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2025-12-31\",\"value_reported\":2000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"BBB","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":1_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"BBB INC\",\"report_period\":\"2026-03-31\",\"value_reported\":1000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"BBB","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":3_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"BBB INC\",\"report_period\":\"2025-12-31\",\"value_reported\":3000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"CCC","action":"HOLDING_13F","whale_name":"Lead B","insider_role":"Manager B","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":4_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager B\",\"lead_investor\":\"Lead B\",\"nameOfIssuer\":\"CCC INC\",\"report_period\":\"2026-03-31\",\"value_reported\":4000000,\"value_unit\":\"thousands_usd\"}"},
    ]
    html = build_html_report(top_scores=[], recent_trades=[], institutional_13f_holdings=holdings, baseline_trade_count=10)
    assert "13F 最新持仓集中度 Top 5" in html
    assert "13F 加仓 / 新建仓集中度 Top 5" in html
    assert "13F 减仓 / 清仓集中度 Top 5" in html
    assert "AAA" in html and "BBB" in html and "CCC" in html
    assert "新建仓" in html


def test_institutional_13f_top20_coverage_table_marks_incomplete_sample():
    html = build_html_report(
        top_scores=[],
        recent_trades=[],
        institutional_13f_holdings=[
            {"ticker":"AAPL","action":"HOLDING_13F","whale_name":"Warren Buffett","insider_role":"Berkshire Hathaway","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":10_000_000_000,"shares":1000000,"raw_json":"{\"manager\":\"Berkshire Hathaway\",\"lead_investor\":\"Warren Buffett\",\"nameOfIssuer\":\"APPLE INC\",\"report_period\":\"2026-03-31\",\"value_reported\":10000000,\"value_unit\":\"thousands_usd\"}"},
        ],
        institutional_13f_status=[{"rank": 1, "manager": "Berkshire Hathaway", "lead_investor": "Warren Buffett", "cik": "1067983", "status": "OK_LATEST_ONLY", "message": "已采集最新期"}],
        baseline_trade_count=10,
    )
    assert "13F Top20 机构采集覆盖率" in html
    assert "目标Top20" in html
    assert "不完整样本" in html
    assert "Berkshire Hathaway" in html
    assert "Pershing Square Capital Management" in html


def test_institutional_13f_amount_guard_repairs_implied_price_1000x_rows():
    holdings = [
        {"ticker":"GOOGL","action":"HOLDING_13F","whale_name":"David Tepper","insider_role":"Appaloosa LP","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":497_040_000_000,"shares":1_732_700,"raw_json":"{\"manager\":\"Appaloosa LP\",\"lead_investor\":\"David Tepper\",\"nameOfIssuer\":\"ALPHABET INC\",\"report_period\":\"2026-03-31\",\"value_reported\":497040000,\"value_unit\":\"thousands_usd\"}"},
    ]
    html = build_html_report(top_scores=[], recent_trades=[], institutional_13f_holdings=holdings, baseline_trade_count=10)
    assert "$497.04M" in html
    assert "$497.04B" not in html


def test_13f_concentration_charts_are_in_first_summary_and_require_two_managers():
    holdings = [
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":5_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2026-03-31\",\"value_reported\":5000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":2_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2025-12-31\",\"value_reported\":2000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead B","insider_role":"Manager B","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":4_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager B\",\"lead_investor\":\"Lead B\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2026-03-31\",\"value_reported\":4000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"AAA","action":"HOLDING_13F","whale_name":"Lead B","insider_role":"Manager B","source":"INSTITUTIONAL_13F","trade_date":"2025-12-31","filing_date":"2026-02-15","amount_usd":3_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager B\",\"lead_investor\":\"Lead B\",\"nameOfIssuer\":\"AAA INC\",\"report_period\":\"2025-12-31\",\"value_reported\":3000000,\"value_unit\":\"thousands_usd\"}"},
        {"ticker":"SOLO","action":"HOLDING_13F","whale_name":"Lead C","insider_role":"Manager C","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":99_000_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager C\",\"lead_investor\":\"Lead C\",\"nameOfIssuer\":\"SOLO INC\",\"report_period\":\"2026-03-31\",\"value_reported\":99000000,\"value_unit\":\"thousands_usd\"}"},
    ]
    html = build_html_report(top_scores=[], recent_trades=[], institutional_13f_holdings=holdings, baseline_trade_count=10)
    first = html[html.index("一、今日结论总览"):html.index("二、商界巨鲸行动")]
    assert "13F 最新持仓集中度 Top 5（按持有机构数）" in first
    assert "13F 加仓 / 新建仓集中度 Top 5（按加仓机构数）" in first
    assert "13F 减仓 / 清仓集中度 Top 5（按减仓机构数）" in first
    assert "AAA" in first
    assert "SOLO" not in first
    assert "2家" in first


def test_13f_detail_table_is_balanced_by_manager_latest_top5():
    holdings = []
    for i in range(7):
        holdings.append({"ticker":f"A{i}","action":"HOLDING_13F","whale_name":"Lead A","insider_role":"Manager A","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":10_000_000_000-i,"shares":10,"raw_json":f"{{\"manager\":\"Manager A\",\"lead_investor\":\"Lead A\",\"nameOfIssuer\":\"A{i} INC\",\"report_period\":\"2026-03-31\",\"value_reported\":{10000000-i},\"value_unit\":\"thousands_usd\"}}"})
    holdings.append({"ticker":"B0","action":"HOLDING_13F","whale_name":"Lead B","insider_role":"Manager B","source":"INSTITUTIONAL_13F","trade_date":"2026-03-31","filing_date":"2026-05-15","amount_usd":1_000_000,"shares":10,"raw_json":"{\"manager\":\"Manager B\",\"lead_investor\":\"Lead B\",\"nameOfIssuer\":\"B0 INC\",\"report_period\":\"2026-03-31\",\"value_reported\":1000,\"value_unit\":\"thousands_usd\"}"})
    html = build_html_report(top_scores=[], recent_trades=[], institutional_13f_holdings=holdings, baseline_trade_count=10)
    detail = html[html.index("机构巨鲸 13F 持仓明细"):]
    assert "Manager A" in detail and "Manager B" in detail
    assert "A0" in detail and "A4" in detail
    assert "A5" not in detail and "A6" not in detail
    assert "B0" in detail
