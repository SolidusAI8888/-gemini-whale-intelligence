from __future__ import annotations

import pandas as pd

from app.collectors import universe


class _Response:
    def __init__(self, text: str = "<html></html>", status_code: int = 200, content: bytes | None = None):
        self.text = text
        self.status_code = status_code
        self.content = content if content is not None else text.encode("utf-8")

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_index_html_fetch_uses_browser_headers(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout):
        seen["url"] = url
        seen["headers"] = headers
        seen["timeout"] = timeout
        return _Response("<table><tr><th>Symbol</th></tr><tr><td>AAPL</td></tr></table>")

    monkeypatch.setattr(universe.requests, "get", fake_get)
    tables = universe._read_html_tables(universe.SP500_URL)

    assert tables[0].iloc[0, 0] == "AAPL"
    assert "Mozilla/5.0" in seen["headers"]["User-Agent"]
    assert seen["timeout"] == 20


def test_full_universe_requires_both_indices(monkeypatch):
    monkeypatch.setattr(universe, "_read_sp500", lambda: {f"S{i}" for i in range(500)})
    monkeypatch.setattr(universe, "_read_nasdaq100", lambda: set())

    assert universe.load_universe_tickers() == universe.FALLBACK_TICKERS


def test_full_universe_unions_sp500_and_nasdaq100(monkeypatch):
    sp500 = {"AAPL", "MSFT", "BRK-B"}
    nasdaq100 = {"AAPL", "NVDA", "GOOG"}
    monkeypatch.setattr(universe, "_read_sp500", lambda: sp500)
    monkeypatch.setattr(universe, "_read_nasdaq100", lambda: nasdaq100)

    assert universe.load_universe_tickers() == {"AAPL", "MSFT", "BRK-B", "NVDA", "GOOG"}


def test_sp500_wikipedia_fallback_rejects_partial_table(monkeypatch):
    monkeypatch.setattr(
        universe,
        "_read_html_tables",
        lambda url: [pd.DataFrame({"Symbol": ["AAPL", "MSFT"]})],
    )

    try:
        universe._read_sp500_wikipedia()
    except RuntimeError as exc:
        assert "refusing partial universe" in str(exc)
    else:
        raise AssertionError("partial S&P 500 table must be rejected")


def test_sp500_prefers_official_state_street_source(monkeypatch):
    official = {f"S{i}" for i in range(500)}
    monkeypatch.setattr(universe, "_read_sp500_primary", lambda: official)
    monkeypatch.setattr(
        universe,
        "_read_sp500_wikipedia",
        lambda: (_ for _ in ()).throw(AssertionError("fallback should not be called")),
    )

    assert universe._read_sp500() == official


def test_sp500_falls_back_when_official_source_fails(monkeypatch):
    fallback = {f"S{i}" for i in range(500)}
    monkeypatch.setattr(
        universe,
        "_read_sp500_primary",
        lambda: (_ for _ in ()).throw(RuntimeError("issuer unavailable")),
    )
    monkeypatch.setattr(universe, "_read_sp500_wikipedia", lambda: fallback)

    assert universe._read_sp500() == fallback


def test_nasdaq_prefers_official_ndx_pdf(monkeypatch):
    official = {f"N{i}" for i in range(100)}
    monkeypatch.setattr(universe, "_read_nasdaq100_primary", lambda: official)
    monkeypatch.setattr(
        universe,
        "_read_nasdaq100_snapshot",
        lambda: (_ for _ in ()).throw(AssertionError("snapshot should not be called")),
    )

    assert universe._read_nasdaq100() == official


def test_nasdaq_live_failure_uses_validated_official_snapshot(monkeypatch):
    snapshot = {f"N{i}" for i in range(101)}
    monkeypatch.setattr(
        universe,
        "_read_nasdaq100_primary",
        lambda: (_ for _ in ()).throw(RuntimeError("Nasdaq endpoint timeout")),
    )
    monkeypatch.setattr(universe, "_read_nasdaq100_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        universe,
        "_read_nasdaq100_wikipedia",
        lambda: (_ for _ in ()).throw(AssertionError("Wikipedia should not be called when snapshot is valid")),
    )

    assert universe._read_nasdaq100() == snapshot


def test_checked_in_nasdaq_snapshot_is_complete_and_contains_key_names():
    snapshot = universe._read_nasdaq100_snapshot()

    assert len(snapshot) >= 95
    assert {"AAPL", "MSFT", "NVDA", "INTC", "GOOGL", "GOOG"} <= snapshot
