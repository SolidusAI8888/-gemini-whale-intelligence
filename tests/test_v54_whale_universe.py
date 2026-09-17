from app.site_data import build_site_payload
from app.whale_universe import CORE_COMPANY_LEADERS, CURRENT_EXECUTIVE_BRANCH, TOP20_INSTITUTIONS, declared_whale_universe


def test_declared_universe_covers_required_groups_without_creating_actions():
    rows = declared_whale_universe()
    names = {row["name"] for row in rows}
    assert "Donald J. Trump" in names
    assert {name for name, _ in CURRENT_EXECUTIVE_BRANCH} <= names
    assert len([row for row in rows if row["category"] == "重点机构"]) >= 20
    assert set(TOP20_INSTITUTIONS) <= names
    corporate_tickers = {ticker for ticker, _, _ in CORE_COMPANY_LEADERS}
    assert len(corporate_tickers) == 19
    for ticker in corporate_tickers:
        roles = " ".join(str(row["role"]) for row in rows if row.get("ticker") == ticker).lower()
        assert any(title in roles for title in ("chair", "lead independent director"))
        assert "ceo" in roles
        assert "cfo" in roles
    assert all(row["tracking_status"] == "scope_only" for row in rows)


def test_universe_is_metadata_not_a_trade_or_holding():
    payload = build_site_payload([], [], [])
    assert payload["whale_universe"]
    assert payload["events"] == []
    assert payload["holdings"] == []
    assert payload["concentration"] == []
    assert payload["holding_concentration"] == []
