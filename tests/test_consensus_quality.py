from app.analyzers.consensus import build_consensus_scores


def test_split_lots_do_not_create_full_consensus():
    trades = []
    for i in range(20):
        trades.append({
            "ticker": "TEST",
            "action": "SELL",
            "whale_name": "Same Insider",
            "whale_category": "Director",
            "accession_number": "0001",
            "amount_usd": 1000,
            "filing_date": "2026-06-01",
        })
    rows = build_consensus_scores(trades)
    assert len(rows) == 1
    assert rows[0]["unique_sell_whales"] == 1
    assert rows[0]["unique_sell_events"] == 1
    assert rows[0]["consensus_score"] < 60
