from app.collectors import _quality_13f_info_table_picker
from app.domain.trade_classification import is_primary_transaction, primary_transactions
from app.reports.v40_oge import build_cabinet_oge_radar, classify_oge_asset
from app.reports.v40_overview import build_daily_changes_overview


def test_political_single_digit_amount_is_not_primary_anywhere():
    row = {
        "source": "POLITICAL_HOUSE",
        "action": "BUY",
        "ticker": "HON",
        "amount_usd": 2,
    }
    assert is_primary_transaction(row) is False
    assert primary_transactions([row]) == []


def test_tiny_broker_affiliate_buy_is_evidence_not_signal():
    row = {
        "source": "SEC Form 4",
        "action": "BUY",
        "transaction_code": "P",
        "ticker": "NMZ",
        "amount_usd": 368,
        "whale_name": "MERRILL LYNCH, PIERCE, FENNER & SMITH INC.",
    }
    assert is_primary_transaction(row) is False


def test_derivative_exercise_labelled_buy_is_excluded():
    row = {
        "source": "SEC_FORM4",
        "action": "BUY",
        "transaction_code": "M",
        "ticker": "AAPL",
        "amount_usd": 1_000_000,
        "raw_json": '{"security_title":"Employee stock option exercise"}',
    }
    assert is_primary_transaction(row) is False


def test_13f_picker_prefers_information_table_and_rejects_cover_only():
    files = [
        "https://sec.example/primary_doc.xml",
        "https://sec.example/form13f.xml",
        "https://sec.example/infotable.xml",
    ]
    assert _quality_13f_info_table_picker(files).endswith("infotable.xml")
    assert _quality_13f_info_table_picker(["https://sec.example/primary_doc.xml"]) is None


def test_oge_radar_drops_pdf_fragments_and_deduplicates_entity():
    common = {
        "source": "OGE_EXECUTIVE_ASSET",
        "action": "HOLDING",
        "whale_name": "Official",
        "filing_url": "https://example.com/278e.pdf",
        "amount_usd": 50_000_000,
        "filing_date": "2026-07-30",
    }
    rows = [
        {**common, "raw_json": '{"asset_name":"RATE TERM"}'},
        {**common, "raw_json": '{"asset_name":"Borrower) N/A Over $50,000,000"}'},
        {**common, "raw_json": '{"asset_name":"2.1 BGC Group, Inc. (BGC) N/A Over $50,000,000"}'},
        {**common, "raw_json": '{"asset_name":"BGC Group, Inc. (BGC) Over $50,000,000"}'},
    ]
    html = build_cabinet_oge_radar(rows)
    assert "RATE TERM" not in html
    assert "Borrower)" not in html
    assert html.count("BGC Group, Inc. (BGC)") == 1
    assert "股票/上市证券" in html


def test_oge_company_and_partnership_categories_are_not_generic():
    stock = {"raw_json": '{"asset_name":"Liberty Energy Inc. (LBRT)"}'}
    partnership = {"raw_json": '{"asset_name":"Cantor Fitzgerald, L.P."}'}
    assert classify_oge_asset(stock) == "股票/上市证券"
    assert classify_oge_asset(partnership) == "私募/LLC/信托"


def test_daily_overview_reserves_space_for_buy_and_oge():
    rows = []
    for index in range(20):
        rows.append({
            "source": "SEC_FORM4",
            "action": "SELL",
            "ticker": f"S{index}",
            "amount_usd": 1_000_000 - index,
            "created_at": "2026-08-05 10:00:00",
        })
    rows.extend([
        {
            "source": "SEC_FORM4",
            "action": "BUY",
            "ticker": "BUY1",
            "amount_usd": 50_000,
            "created_at": "2026-08-05 10:00:00",
        },
        {
            "source": "OGE_EXECUTIVE_ASSET",
            "action": "HOLDING",
            "whale_name": "Official",
            "amount_usd": 100_000,
            "created_at": "2026-08-05 10:00:00",
            "raw_json": '{"asset_name":"Example Trust"}',
        },
    ])
    html = build_daily_changes_overview(rows, new_since="2026-08-05 09:00:00", limit=10)
    assert "主动买入 1" in html
    assert "行政分支资产披露 1" in html
    assert "BUY1" in html
    assert "Example Trust" in html
