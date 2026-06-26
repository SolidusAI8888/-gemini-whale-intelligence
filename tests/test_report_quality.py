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
