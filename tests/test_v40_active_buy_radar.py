from app.reports.v40_report import apply_v40_report_layout, build_active_buy_radar


def _trade(**overrides):
    row = {
        "ticker": "AAPL",
        "action": "BUY",
        "transaction_code": "P",
        "trade_date": "2026-07-30",
        "filing_date": "2026-07-31",
        "source_id": "same-economic-trade",
        "source": "SEC_FORM4",
        "amount_usd": 100000,
        "shares": 500,
        "price": 200,
        "whale_name": "Buyer One",
        "created_at": "2026-07-31 10:00:00",
    }
    row.update(overrides)
    return row


def test_active_buy_radar_deduplicates_joint_reporters_and_amount():
    rows = [
        _trade(whale_name="Buyer One"),
        _trade(whale_name="Buyer Two"),
    ]

    html = build_active_buy_radar(rows, new_since="2026-07-31 09:00:00")

    assert "主动买入雷达（P/BUY，按去重买入金额）" in html
    assert "$100.0K" in html
    assert "$200.0K" not in html
    assert "Buyer One" in html
    assert "Buyer Two" in html
    assert "股票/直接买入" in html
    assert 'class="row-new"' in html


def test_active_buy_radar_excludes_sell_and_holding_rows():
    rows = [
        _trade(action="SELL", source_id="sell"),
        _trade(action="HOLDING", source="OGE_EXECUTIVE_ASSET", source_id="holding"),
    ]

    html = build_active_buy_radar(rows)

    assert "暂无金额口径可信的主动买入交易" in html
    assert "AAPL</b></td>" not in html


def test_active_buy_radar_labels_congressional_call_option():
    row = _trade(
        ticker="MSFT",
        source="POLITICAL_HOUSE",
        source_id="pelosi-msft-option",
        amount_usd=3_000_000,
        whale_name="Nancy Pelosi",
        raw_json={
            "asset_type": "Option",
            "option_type": "Call",
            "description": "Purchased call options in MSFT",
        },
    )

    html = build_active_buy_radar([row])

    assert "MSFT" in html
    assert "Nancy Pelosi" in html
    assert "Call Option" in html
    assert "$3.00M" in html


def test_v40_layout_removes_legacy_net_column_and_injects_before_first_section():
    legacy = """
    <html><body><h1>Report</h1>
    <table><thead><tr><th>股票</th><th>BUY金额</th><th>净额</th></tr></thead>
    <tbody><tr><td>AAPL</td><td>$100</td><td>$80</td></tr></tbody></table>
    <h2>旧章节</h2></body></html>
    """

    updated = apply_v40_report_layout(legacy, [_trade()])

    assert "<th>净额</th>" not in updated
    assert "<td>$80</td>" not in updated
    assert updated.index("主动买入雷达") < updated.index("旧章节")
