from app.site_market_history import parse_chart_payload


def test_parse_chart_payload_keeps_only_real_timestamped_closes():
    points, market = parse_chart_payload({
        "chart": {"result": [{
            "timestamp": [0, 86_400, 172_800],
            "indicators": {"quote": [{"close": [10.0, None, 12.0]}]},
            "meta": {"regularMarketPrice": 12.0, "chartPreviousClose": 2.0},
        }]},
    })
    assert points == [
        {"date": "1970-01-01", "close": 10.0},
        {"date": "1970-01-03", "close": 12.0},
    ]
    assert market["price"] == 12.0
    assert round(market["change_pct"], 2) == 20.0


def test_parse_chart_payload_fails_closed_on_missing_series():
    assert parse_chart_payload({"chart": {"result": []}}) == ([], None)
