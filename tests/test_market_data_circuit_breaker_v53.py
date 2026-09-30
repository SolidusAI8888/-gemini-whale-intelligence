from __future__ import annotations

import requests

from app.collectors import market_data


class _Response:
    def __init__(self, status_code: int, *, url: str, text: str = "", payload=None):
        self.status_code = status_code
        self.url = url
        self.text = text
        self._payload = {} if payload is None else payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

    def json(self):
        return self._payload


def test_v53_explicit_403_opens_endpoint_circuit(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=20):
        calls["count"] += 1
        return _Response(
            403,
            url=f"{url}?symbol={params.get('symbol')}",
            text='{"error":"You do not have access"}',
        )

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    market_data._reset_market_api_circuits()

    url = "https://finnhub.io/api/v1/news-sentiment"
    assert market_data._safe_get_json(url, {"symbol": "MSFT", "token": "x"}) is None
    assert market_data._safe_get_json(url, {"symbol": "AAPL", "token": "x"}) is None
    assert calls["count"] == 1


def test_v53_repeated_timeout_opens_endpoint_circuit_after_two_failures(monkeypatch):
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=20):
        calls["count"] += 1
        raise requests.Timeout("slow provider")

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    market_data._reset_market_api_circuits()

    url = "https://www.alphavantage.co/query"
    params = {"function": "GLOBAL_QUOTE", "symbol": "MSFT", "apikey": "x"}
    assert market_data._safe_get_json(url, params) is None
    params["symbol"] = "AAPL"
    assert market_data._safe_get_json(url, params) is None
    params["symbol"] = "NVDA"
    assert market_data._safe_get_json(url, params) is None
    assert calls["count"] == 2
