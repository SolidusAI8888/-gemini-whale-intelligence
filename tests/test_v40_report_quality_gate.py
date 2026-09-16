from app.reports.v40_oge import build_cabinet_oge_radar
from app.reports.v40_report import apply_v40_report_layout, build_active_buy_radar


def test_oge_future_date_is_not_published_as_fact():
    html = build_cabinet_oge_radar([
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "insider_role": "Secretary",
            "filing_date": "2027-08-31",
            "amount_usd": 3_000_000,
            "raw_json": '{"asset_name":"Example Holdings LLC","amount_range_label":"$1,000,001-$5,000,000"}',
        }
    ])
    assert "日期待核验" in html
    assert "2027-08-31" not in html


def test_oge_fragment_rows_are_filtered():
    html = build_cabinet_oge_radar([
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "raw_json": '{"asset_name":"N/A None (or less"}',
        },
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "raw_json": '{"asset_name":"Example Real Estate LLC","description":"commercial real estate"}',
        },
    ])
    assert "None (or less" not in html
    assert "Example Real Estate LLC" in html


def test_dubious_political_two_dollar_buy_is_excluded():
    html = build_active_buy_radar([
        {
            "source": "POLITICAL_HOUSE",
            "action": "BUY",
            "ticker": "HON",
            "amount_usd": 2,
            "whale_name": "Example Member",
            "trade_date": "2026-07-30",
        },
        {
            "source": "POLITICAL_HOUSE",
            "action": "BUY",
            "ticker": "V",
            "amount_usd": 8000,
            "whale_name": "Example Member",
            "trade_date": "2026-07-10",
        },
    ])
    assert "HON" not in html
    assert "<b>V</b>" in html


def test_layout_removes_duplicate_legacy_overview_and_old_highlight(monkeypatch):
    monkeypatch.setattr("app.reports.v40_report._oge_rows", lambda: [])
    monkeypatch.setattr("app.reports.v40_report._institutional_rows", lambda: [])
    legacy = (
        "<html><body><h1>Report</h1>"
        "<h2>一、今日结论总览</h2>"
        "<h3>今日新增内容总览（相对上一轮成功运行）</h3><p>旧内容</p>"
        "<h3>13F状态</h3><table><tbody><tr class=\"row-new\"><td>解析0行</td></tr></tbody></table>"
        "</body></html>"
    )
    rendered = apply_v40_report_layout(legacy, [], new_since=None)
    assert rendered.count("今日新增内容总览") == 1
    assert "旧内容" not in rendered
    assert '<tr class="row-new"><td>解析0行' not in rendered
