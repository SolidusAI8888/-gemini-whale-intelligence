from __future__ import annotations

import pandas as pd

from app.collectors import universe


class _Response:
    def __init__(self, text: str = "<html></html>", status_code: int = 200):
        self.text = text
        self.status_code = status_code

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
    assert seen["timeout"] == 30


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


def test_sp500_rejects_partial_table(monkeypatch):
    monkeypatch.setattr(
        universe,
        "_read_html_tables",
        lambda url: [pd.DataFrame({"Symbol": ["AAPL", "MSFT"]})],
    )

    try:
        universe._read_sp500()
    except RuntimeError as exc:
        assert "refusing partial universe" in str(exc)
    else:
        raise AssertionError("partial S&P 500 table must be rejected")
