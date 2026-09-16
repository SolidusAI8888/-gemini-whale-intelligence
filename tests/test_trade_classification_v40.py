from app.domain.trade_classification import (
    is_asset_or_holding_disclosure,
    is_primary_transaction,
    primary_transactions,
)


def test_oge_asset_is_not_a_primary_transaction():
    row = {"source": "OGE_EXECUTIVE_ASSET", "action": "HOLDING", "ticker": ""}
    assert is_asset_or_holding_disclosure(row) is True
    assert is_primary_transaction(row) is False


def test_13f_holding_is_not_a_primary_transaction():
    row = {"source": "INSTITUTIONAL_13F", "action": "HOLDING_13F", "ticker": "AAPL"}
    assert is_asset_or_holding_disclosure(row) is True
    assert is_primary_transaction(row) is False


def test_real_buy_and_sell_rows_remain_primary_transactions():
    assert is_primary_transaction({"source": "POLITICAL_HOUSE", "action": "BUY"}) is True
    assert is_primary_transaction({"source": "SEC_FORM4", "action": "SELL"}) is True
    assert is_primary_transaction({"source": "POLITICAL_HOUSE", "action": "EXCHANGE"}) is True


def test_holding_action_is_excluded_even_with_transaction_like_source():
    row = {"source": "OGE_EXECUTIVE", "action": "HOLDING", "ticker": "MSFT"}
    assert is_primary_transaction(row) is False


def test_primary_transactions_filters_without_mutating_input():
    rows = [
        {"source": "SEC_FORM4", "action": "BUY", "ticker": "NVDA"},
        {"source": "OGE_EXECUTIVE_ASSET", "action": "HOLDING", "ticker": ""},
        {"source": "INSTITUTIONAL_13F", "action": "HOLDING_13F", "ticker": "AAPL"},
        {"source": "POLITICAL_HOUSE", "action": "SELL", "ticker": "TSLA"},
    ]

    filtered = primary_transactions(rows)

    assert [row["ticker"] for row in filtered] == ["NVDA", "TSLA"]
    assert filtered[0] is not rows[0]
    assert len(rows) == 4
