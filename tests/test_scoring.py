from app.analyzers.consensus import build_consensus_scores
from app.analyzers.opportunity import score_opportunities
from app.analyzers.whale_score import calculate_trade_whale_score


def test_trade_score_buy_ceo():
    trade = {
        "whale_category": "CEO",
        "action": "BUY",
        "amount_usd": 1_000_000,
        "filing_date": "2099-01-01",
    }
    assert calculate_trade_whale_score(trade) > 60


def test_consensus_and_opportunity():
    trades = [
        {"ticker": "NVDA", "whale_name": "A", "whale_category": "CEO", "action": "BUY", "amount_usd": 1_000_000, "filing_date": "2099-01-01"},
        {"ticker": "NVDA", "whale_name": "B", "whale_category": "Director", "action": "BUY", "amount_usd": 500_000, "filing_date": "2099-01-01"},
    ]
    consensus = build_consensus_scores(trades)
    scores = score_opportunities(consensus)
    assert scores[0]["ticker"] == "NVDA"
    assert scores[0]["opportunity_score"] > 50
