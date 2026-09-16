from __future__ import annotations

from app.collectors.sec_13f_v43 import normalize_13f_row_for_tests
from app.reports.v40_oge import build_cabinet_oge_radar
from app.reports.v40_report import replace_header_change_count_for_tests, trusted_new_count_for_tests


def test_noisy_oge_row_keeps_real_bank_entity():
    rows = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "insider_role": "Cabinet",
            "filing_url": "https://example.com/report.pdf",
            "source_id": "oge-1",
            "amount_usd": 50_000_000,
            "raw_json": {
                "asset_name": "N/A On Demand 3 Bank of America, N.A See Endnote Over $50,000,000",
                "amount_range_label": ">$50,000,000",
            },
        }
    ]
    html = build_cabinet_oge_radar(rows)
    assert html.count("Bank of America, N.A.") == 1
    assert "On Demand" not in html.split("<tbody>", 1)[-1]


def test_pure_oge_noise_never_reaches_radar():
    noisy = ["Dividends $100,001", "Crop Sales $51,180", "Over $50,000,000", "# EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE"]
    rows = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "source_id": f"oge-{i}",
            "amount_usd": 1_000_000,
            "raw_json": {"asset_name": text},
        }
        for i, text in enumerate(noisy)
    ]
    html = build_cabinet_oge_radar(rows)
    for text in noisy:
        assert text not in html
    assert "暂无通过质量校验" in html


def test_modern_13f_value_is_dollars_not_thousands():
    row = {
        "source": "INSTITUTIONAL_13F",
        "action": "HOLDING_13F",
        "amount_usd": 43_197_450_000_000,
        "trade_date": "2026-06-30",
        "raw_json": {
            "report_period": "2026-06-30",
            "value_reported": 43_197_450_000,
            "value_unit": "thousands_usd",
        },
    }
    normalized = normalize_13f_row_for_tests(row)
    assert normalized["amount_usd"] == 43_197_450_000
    assert "thousands_usd" not in normalized["raw_json"]
    assert '"value_unit": "usd"' in normalized["raw_json"]


def test_header_uses_same_trusted_new_count_basis():
    new_since = "2026-08-09 10:00:00"
    primary = [
        {
            "source": "POLITICAL_HOUSE",
            "action": "BUY",
            "transaction_code": "P",
            "ticker": "MSFT",
            "amount_usd": 8_000,
            "created_at": "2026-08-09 10:01:00",
        }
    ]
    oge = [
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "created_at": "2026-08-09 10:01:00",
            "raw_json": {"asset_name": "Dividends $100,001"},
        }
    ]
    institutional = [
        {
            "source": "INSTITUTIONAL_13F",
            "action": "HOLDING_13F",
            "created_at": "2026-08-09 10:01:00",
        }
    ]
    count = trusted_new_count_for_tests(primary, oge, institutional, new_since)
    assert count == 2
    html = '<div class="big-change">今日新增/变化披露记录：999 条</div><p class="small">变化口径：旧口径。</p>'
    updated = replace_header_change_count_for_tests(html, count)
    assert "今日新增/变化可信记录：2 条" in updated
    assert "与“今日新增内容总览”完全一致" in updated
