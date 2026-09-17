from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any, Iterable

import requests

from app.db import get_conn, init_db
from app.site_data import CORE_ASSETS

log = logging.getLogger(__name__)

YAHOO_SYMBOLS = {
    "BTC": "BTC-USD",
    # SPCX is the user's private SpaceX watch item, not the similarly named ETF.
    # PURR has no unambiguous Yahoo instrument and remains intentionally blank.
}
NO_PUBLIC_MARKET_SYMBOL = {"SPCX", "PURR"}


def parse_chart_payload(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    results = ((payload.get("chart") or {}).get("result") or [])
    if not results:
        return [], None
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    has_ohlc = all(key in quote for key in ("open", "high", "low"))
    opens = quote.get("open") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    points = []
    for index, timestamp in enumerate(timestamps):
        close = closes[index] if index < len(closes) else None
        if close is None:
            continue
        if has_ohlc:
            values = [series[index] if index < len(series) else None for series in (opens, highs, lows)]
            if any(value is None for value in values):
                continue
            open_price, high, low = (float(value) for value in values)
        point = {
            "date": datetime.fromtimestamp(int(timestamp), UTC).date().isoformat(),
            "close": round(float(close), 6),
        }
        if has_ohlc:
            point.update({
                "open": round(open_price, 6), "high": round(high, 6), "low": round(low, 6),
                "volume": float(volumes[index]) if index < len(volumes) and volumes[index] is not None else None,
            })
        points.append(point)
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None and points:
        price = points[-1]["close"]
    change_pct = None
    if len(points) >= 2 and points[-2]["close"]:
        change_pct = (float(points[-1]["close"]) / float(points[-2]["close"]) - 1) * 100
    market = None if price is None else {
        "price": float(price),
        "change_pct": change_pct,
        "data_sources": "yahoo_chart",
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    return points, market


def refresh_site_market_history(tickers: Iterable[str] = CORE_ASSETS, start_date: str = "2025-01-01") -> tuple[int, int]:
    init_db()
    priced = 0
    point_count = 0
    with get_conn() as conn:
        for ticker in tickers:
            ticker = str(ticker).upper()
            if ticker in NO_PUBLIC_MARKET_SYMBOL:
                continue
            symbol = YAHOO_SYMBOLS.get(ticker, ticker)
            try:
                response = requests.get(
                    f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                    params={
                        "period1": int(datetime.fromisoformat(start_date).replace(tzinfo=UTC).timestamp()),
                        "period2": int((datetime.now(UTC) + timedelta(days=1)).timestamp()),
                        "interval": "1d",
                        "events": "history",
                    },
                    headers={"User-Agent": "Mozilla/5.0 WhaleIntelligence/1.0"},
                    timeout=30,
                )
                response.raise_for_status()
                points, market = parse_chart_payload(response.json())
            except Exception as exc:  # noqa: BLE001 - one unsupported symbol must not abort all assets
                log.warning("Site market history unavailable for %s: %s", ticker, exc)
                continue
            if market:
                conn.execute(
                    """
                    INSERT INTO market_snapshots (ticker, price, change_pct, data_sources, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(ticker) DO UPDATE SET
                        price=excluded.price,
                        change_pct=excluded.change_pct,
                        data_sources=excluded.data_sources,
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (ticker, market["price"], market["change_pct"], market["data_sources"]),
                )
                priced += 1
            for point in points:
                conn.execute(
                    """
                    INSERT INTO market_price_history
                        (ticker, price_date, open, high, low, close, volume, source, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'yahoo_chart', CURRENT_TIMESTAMP)
                    ON CONFLICT(ticker, price_date) DO UPDATE SET
                        open=excluded.open, high=excluded.high, low=excluded.low,
                        close=excluded.close, volume=excluded.volume,
                        source=excluded.source, updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        ticker, point["date"], point["open"], point["high"],
                        point["low"], point["close"], point["volume"],
                    ),
                )
            point_count += len(points)
        conn.commit()
    return priced, point_count


if __name__ == "__main__":
    prices, points = refresh_site_market_history()
    print(f"priced_assets={prices} price_points={points}")
