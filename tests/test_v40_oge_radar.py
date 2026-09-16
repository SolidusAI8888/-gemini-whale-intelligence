from app.reports.v40_oge import build_cabinet_oge_radar


def test_oge_radar_keeps_non_ticker_assets_and_categories():
    rows = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Cabinet Official",
            "insider_role": "Secretary",
            "amount_usd": 250000,
            "filing_date": "2026-07-30",
            "filing_url": "https://example.com/oge",
            "raw_json": '{"asset_name":"Example Real Estate LLC","description":"commercial real estate holding","amount_range_label":"$100,001-$500,000","report_type":"OGE 278e"}',
        },
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "DISCLOSURE",
            "whale_name": "Cabinet Official",
            "insider_role": "Secretary",
            "amount_usd": 50000,
            "filing_date": "2026-07-30",
            "raw_json": '{"asset_name":"Bitcoin custody account","description":"digital asset","amount_range_label":"$15,001-$50,000"}',
        },
    ]

    html = build_cabinet_oge_radar(rows)

    assert "部长 / Cabinet OGE 披露雷达" in html
    assert "Example Real Estate LLC" in html
    assert "房地产/商业权益" in html
    assert "Bitcoin custody account" in html
    assert "加密资产" in html
    assert "股票代码" not in html


def test_oge_radar_marks_new_rows_orange():
    rows = [{
        "source": "OGE_EXECUTIVE_ASSET",
        "action": "HOLDING",
        "whale_name": "Official",
        "filing_date": "2026-07-31",
        "created_at": "2026-07-31 17:00:00",
        "raw_json": '{"asset_name":"Treasury bond","description":"U.S. Treasury note"}',
    }]

    html = build_cabinet_oge_radar(rows, new_since="2026-07-31 16:00:00")
    assert 'class="row-new"' in html
    assert "债券" in html
