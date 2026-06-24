from app.reports.html_report import build_html_report


def test_report_splits_buy_and_sell_sections():
    html = build_html_report(
        top_scores=[
            {"ticker":"BUYME","signal_label":"多头 B级","opportunity_score":66,"consensus_score":50,"risk_score":0,"explanation":"buy"},
            {"ticker":"SELLME","signal_label":"减持/卖出预警 B级","opportunity_score":70,"consensus_score":60,"risk_score":0,"explanation":"sell"},
        ],
        recent_trades=[
            {"ticker":"BUYME","action":"BUY","transaction_code":"P"},
            {"ticker":"GRANT","action":"GRANT_OR_AWARD","transaction_code":"A"},
        ],
        ai_analysis="ok",
        new_trade_count=1,
    )
    assert "主动买入雷达" in html
    assert "减持/卖出预警 Top Signals" in html
    assert "BUYME" in html
    assert "SELLME" in html
    assert "GRANT_OR_AWARD" not in html
