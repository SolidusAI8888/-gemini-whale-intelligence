from app.intelligence.models import Signal, SignalDirection, SignalSource
from app.intelligence.ranking import build_rankings
from app.intelligence.score_engine import score_signals
from app.intelligence.signal import normalize_trade


def sig(ticker, source, direction, actor, amount=1_000_000, day="2026-07-22"):
    return Signal(ticker, source, direction, actor, "test", day, amount, confidence=0.8)


def test_missing_source_is_na_and_dynamic_weights_are_renormalized():
    score = score_signals([
        sig("MSFT", SignalSource.INSTITUTIONAL_13F, SignalDirection.BULLISH, "Fund"),
        sig("MSFT", SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
    ])[0]
    assert score.form4_score is None
    assert score.institutional_score is not None
    assert score.congress_score is not None
    assert score.coverage_count == 2
    assert score.coverage_label == "2/3 Sources"
    assert score.wis_score > 75


def test_conflicted_resonance_is_signed_and_explained():
    score = score_signals([
        sig("NVDA", SignalSource.FORM4, SignalDirection.BEARISH, "CEO"),
        sig("NVDA", SignalSource.INSTITUTIONAL_13F, SignalDirection.BULLISH, "Fund"),
        sig("NVDA", SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
    ])[0]
    assert score.resonance_direction == "CONFLICTED"
    assert score.resonance_level == 1
    assert score.resonance_signed_score > 0
    assert set(score.resonance_sources) == {"FORM4", "13F", "CONGRESS_OGE"}


def test_risk_engine_is_not_inverse_of_wis():
    score = score_signals([
        sig("AMD", SignalSource.FORM4, SignalDirection.BEARISH, "CEO"),
        sig("AMD", SignalSource.INSTITUTIONAL_13F, SignalDirection.BEARISH, "Fund"),
    ])[0]
    assert score.risk_score > 50
    assert round(score.risk_score, 2) != round(100 - score.wis_score, 2)


def test_single_source_is_excluded_from_opportunity_without_exceptional_confidence():
    score = score_signals([
        sig("AAPL", SignalSource.FORM4, SignalDirection.BULLISH, "CEO", amount=1_000),
    ])[0]
    rankings = build_rankings([score])
    assert rankings["opportunities"] == []
    assert rankings["risks"]


def test_verified_cusip_maps_to_ticker():
    signal = normalize_trade({
        "ticker": "CUSIP:007903107",
        "source": "INSTITUTIONAL_13F",
        "action": "BUY",
        "whale_name": "Fund",
        "trade_date": "2026-07-22",
    })
    assert signal is not None
    assert signal.ticker == "AMD"


def test_lrcx_current_cusip_maps_before_scoring():
    signal = normalize_trade({
        "ticker": "CUSIP:512807306",
        "source": "INSTITUTIONAL_13F",
        "action": "13F_INCREASE",
        "whale_name": "Fund",
        "trade_date": "2026-06-30",
    })
    assert signal is not None
    assert signal.ticker == "LRCX"


def test_13f_holdings_generate_directional_delta_signal():
    from app.intelligence.signal import normalize_trades
    rows = [
        {
            "ticker": "CUSIP:007903107", "source": "INSTITUTIONAL_13F", "action": "HOLDING_13F",
            "whale_name": "Lead", "insider_role": "Manager A", "trade_date": "2026-03-31",
            "amount_usd": 100_000_000, "raw_json": '{"manager":"Manager A","report_period":"2026-03-31","cusip":"007903107"}',
        },
        {
            "ticker": "CUSIP:007903107", "source": "INSTITUTIONAL_13F", "action": "HOLDING_13F",
            "whale_name": "Lead", "insider_role": "Manager A", "trade_date": "2025-12-31",
            "amount_usd": 40_000_000, "raw_json": '{"manager":"Manager A","report_period":"2025-12-31","cusip":"007903107"}',
        },
    ]
    signals = normalize_trades(rows)
    assert len(signals) == 1
    assert signals[0].ticker == "AMD"
    assert signals[0].source is SignalSource.INSTITUTIONAL_13F
    assert signals[0].direction is SignalDirection.BULLISH
    assert signals[0].action == "13F_INCREASE"
    assert signals[0].amount_usd == 60_000_000


def test_congress_and_oge_are_one_political_resonance_pillar():
    score = score_signals([
        sig("MSFT", SignalSource.CONGRESS, SignalDirection.BULLISH, "Member"),
        sig("MSFT", SignalSource.OGE, SignalDirection.BULLISH, "Cabinet"),
    ])[0]
    assert score.coverage_count == 1
    assert score.resonance_level == 0
    assert score.resonance_direction == "NONE"
    assert score.resonance_signed_score == 0


def test_single_source_perfect_score_is_coverage_discounted_and_excluded():
    score = score_signals([
        sig("HD", SignalSource.CONGRESS, SignalDirection.BULLISH, f"Member {i}", amount=10_000_000, day="2026-07-22")
        for i in range(11)
    ])[0]
    assert score.wis_score >= 95
    assert score.opportunity_score <= 72.1
    assert build_rankings([score])["opportunities"] == []
