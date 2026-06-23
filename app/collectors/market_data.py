from __future__ import annotations

from datetime import date, datetime, timedelta
import logging
from typing import Any, Iterable

import requests

from app.config import settings

log = logging.getLogger(__name__)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        s = str(value).replace(",", "").replace("%", "").strip()
        if s in {"", "None", "null", "nan", "-"}:
            return None
        return float(s)
    except Exception:  # noqa: BLE001
        return None


def _safe_get_json(url: str, params: dict[str, Any], *, timeout: int = 20) -> dict[str, Any] | list[Any] | None:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code in {401, 402, 403, 429}:
            log.warning("Market API restricted/throttled: status=%s url=%s body=%s", response.status_code, response.url.split("apikey=")[0] if "apikey=" in response.url else response.url, response.text[:180])
            return None
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("Market API request failed url=%s error=%s", url, exc)
        return None


def _alpha_global_quote(symbol: str) -> dict[str, Any]:
    if not settings.alpha_vantage_api_key:
        return {}
    data = _safe_get_json(
        "https://www.alphavantage.co/query",
        {"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": settings.alpha_vantage_api_key},
    )
    if not isinstance(data, dict):
        return {}
    quote = data.get("Global Quote") or {}
    if not quote:
        # Alpha Vantage often returns Note/Information when quota is exhausted.
        msg = data.get("Note") or data.get("Information")
        if msg:
            log.warning("Alpha Vantage quote unavailable for %s: %s", symbol, str(msg)[:180])
        return {}
    return {
        "price": _as_float(quote.get("05. price")),
        "change_pct": _as_float(quote.get("10. change percent")),
        "volume": _as_float(quote.get("06. volume")),
        "as_of": quote.get("07. latest trading day"),
    }


def _alpha_overview(symbol: str) -> dict[str, Any]:
    if not settings.alpha_vantage_api_key or not settings.alpha_overview_enabled:
        return {}
    data = _safe_get_json(
        "https://www.alphavantage.co/query",
        {"function": "OVERVIEW", "symbol": symbol, "apikey": settings.alpha_vantage_api_key},
    )
    if not isinstance(data, dict) or not data or data.get("Information"):
        if isinstance(data, dict) and data.get("Information"):
            log.warning("Alpha Vantage overview unavailable for %s: %s", symbol, str(data.get("Information"))[:180])
        return {}
    return {
        "pe_ratio": _as_float(data.get("PERatio")),
        "peg_ratio": _as_float(data.get("PEGRatio")),
        "revenue_growth_yoy": _as_float(data.get("QuarterlyRevenueGrowthYOY")),
        "profit_margin": _as_float(data.get("ProfitMargin")),
        "market_cap": _as_float(data.get("MarketCapitalization")),
        "sector": data.get("Sector"),
        "industry": data.get("Industry"),
    }


def _alpha_daily_technical(symbol: str) -> dict[str, Any]:
    if not settings.alpha_vantage_api_key or not settings.alpha_daily_enabled:
        return {}
    data = _safe_get_json(
        "https://www.alphavantage.co/query",
        {"function": "TIME_SERIES_DAILY", "symbol": symbol, "outputsize": "compact", "apikey": settings.alpha_vantage_api_key},
    )
    if not isinstance(data, dict):
        return {}
    series = data.get("Time Series (Daily)") or {}
    if not series:
        msg = data.get("Note") or data.get("Information")
        if msg:
            log.warning("Alpha Vantage daily unavailable for %s: %s", symbol, str(msg)[:180])
        return {}
    points: list[tuple[str, float]] = []
    for day, values in sorted(series.items(), reverse=True):
        close = _as_float(values.get("4. close"))
        if close is not None:
            points.append((day, close))
    if not points:
        return {}
    latest_date, latest_close = points[0]
    closes = [p[1] for p in points]
    def pct_from(idx: int) -> float | None:
        if len(closes) <= idx or closes[idx] == 0:
            return None
        return (latest_close / closes[idx] - 1.0) * 100.0
    sma20 = sum(closes[:20]) / 20 if len(closes) >= 20 else None
    sma50 = sum(closes[:50]) / 50 if len(closes) >= 50 else None
    return {
        "price": latest_close,
        "as_of": latest_date,
        "ret_20d": pct_from(20),
        "ret_60d": pct_from(60),
        "sma20": sma20,
        "sma50": sma50,
    }


def _finnhub_quote(symbol: str) -> dict[str, Any]:
    if not settings.finnhub_api_key:
        return {}
    data = _safe_get_json(
        "https://finnhub.io/api/v1/quote",
        {"symbol": symbol, "token": settings.finnhub_api_key},
    )
    if not isinstance(data, dict) or not data:
        return {}
    return {
        "price": _as_float(data.get("c")),
        "change_pct": _as_float(data.get("dp")),
        "as_of": datetime.utcfromtimestamp(int(data.get("t") or 0)).date().isoformat() if data.get("t") else None,
    }


def _finnhub_basic_financials(symbol: str) -> dict[str, Any]:
    if not settings.finnhub_api_key or not settings.finnhub_basic_financials_enabled:
        return {}
    data = _safe_get_json(
        "https://finnhub.io/api/v1/stock/metric",
        {"symbol": symbol, "metric": "all", "token": settings.finnhub_api_key},
    )
    if not isinstance(data, dict):
        return {}
    metric = data.get("metric") or {}
    return {
        "pe_ratio": _as_float(metric.get("peNormalizedAnnual") or metric.get("peTTM")),
        "ps_ratio": _as_float(metric.get("psTTM")),
        "revenue_growth_yoy": _as_float(metric.get("revenueGrowthTTMYoy")),
        "gross_margin": _as_float(metric.get("grossMarginTTM")),
        "net_margin": _as_float(metric.get("netProfitMarginTTM")),
        "beta": _as_float(metric.get("beta")),
        "week_52_high": _as_float(metric.get("52WeekHigh")),
        "week_52_low": _as_float(metric.get("52WeekLow")),
    }


def _finnhub_news_sentiment(symbol: str) -> dict[str, Any]:
    if not settings.finnhub_api_key or not settings.finnhub_news_enabled:
        return {}
    data = _safe_get_json(
        "https://finnhub.io/api/v1/news-sentiment",
        {"symbol": symbol, "token": settings.finnhub_api_key},
    )
    if not isinstance(data, dict):
        return {}
    sentiment = data.get("sentiment") or {}
    return {
        "news_buzz": _as_float((data.get("buzz") or {}).get("buzz")),
        "news_sentiment_score": _as_float(sentiment.get("bullishPercent") or sentiment.get("companyNewsScore")),
        "news_bearish_percent": _as_float(sentiment.get("bearishPercent")),
    }


def _finnhub_insider_summary(symbol: str) -> dict[str, Any]:
    if not settings.finnhub_api_key or not settings.finnhub_insider_enabled:
        return {}
    end = date.today()
    start = end - timedelta(days=settings.lookback_days)
    data = _safe_get_json(
        "https://finnhub.io/api/v1/stock/insider-transactions",
        {"symbol": symbol, "from": start.isoformat(), "to": end.isoformat(), "token": settings.finnhub_api_key},
    )
    if not isinstance(data, dict):
        return {}
    rows = data.get("data") or []
    buy_count = sell_count = 0
    buy_amount = sell_amount = 0.0
    for row in rows:
        code = str(row.get("transactionCode") or row.get("transaction") or "").upper()
        shares = abs(_as_float(row.get("share") or row.get("change")) or 0.0)
        price = _as_float(row.get("transactionPrice") or row.get("price")) or 0.0
        amount = shares * price
        if code in {"P", "BUY", "PURCHASE"}:
            buy_count += 1
            buy_amount += amount
        elif code in {"S", "SELL", "SALE"}:
            sell_count += 1
            sell_amount += amount
    return {
        "finnhub_insider_buy_count": buy_count,
        "finnhub_insider_sell_count": sell_count,
        "finnhub_insider_buy_amount": buy_amount,
        "finnhub_insider_sell_amount": sell_amount,
    }


def _market_quality_scores(row: dict[str, Any]) -> tuple[float | None, float | None, float | None, str]:
    notes: list[str] = []
    trend = None
    valuation = None
    sentiment = None

    ret20 = _as_float(row.get("ret_20d"))
    ret60 = _as_float(row.get("ret_60d"))
    price = _as_float(row.get("price"))
    sma20 = _as_float(row.get("sma20"))
    sma50 = _as_float(row.get("sma50"))
    if ret20 is not None or ret60 is not None or (price and sma20):
        trend = 50.0
        if ret20 is not None:
            trend += max(-20, min(20, ret20)) * 0.8
            notes.append(f"20日={ret20:.1f}%")
        if ret60 is not None:
            trend += max(-25, min(25, ret60)) * 0.5
            notes.append(f"60日={ret60:.1f}%")
        if price is not None and sma20:
            trend += 5 if price >= sma20 else -5
        if price is not None and sma50:
            trend += 5 if price >= sma50 else -5
        trend = max(0.0, min(100.0, trend))

    pe = _as_float(row.get("pe_ratio"))
    ps = _as_float(row.get("ps_ratio"))
    growth = _as_float(row.get("revenue_growth_yoy"))
    margin = _as_float(row.get("profit_margin") or row.get("net_margin") or row.get("gross_margin"))
    if pe is not None or ps is not None or growth is not None:
        valuation = 50.0
        if pe is not None:
            if pe <= 0:
                valuation -= 10
            elif pe < 20:
                valuation += 10
            elif pe > 60:
                valuation -= 15
            elif pe > 40:
                valuation -= 7
            notes.append(f"PE={pe:.1f}")
        if ps is not None:
            if ps < 5:
                valuation += 6
            elif ps > 15:
                valuation -= 10
            notes.append(f"PS={ps:.1f}")
        if growth is not None:
            valuation += max(-10, min(15, growth * 25 if abs(growth) <= 2 else growth * 0.25))
            notes.append(f"营收增速={growth:.1%}" if abs(growth) <= 2 else f"营收增速={growth:.1f}%")
        if margin is not None and margin > 0:
            valuation += min(10, margin * 20 if margin <= 2 else margin * 0.2)
        valuation = max(0.0, min(100.0, valuation))

    news = _as_float(row.get("news_sentiment_score"))
    bearish = _as_float(row.get("news_bearish_percent"))
    if news is not None or bearish is not None:
        sentiment = 50.0
        if news is not None:
            sentiment += (news - 0.5) * 50 if 0 <= news <= 1 else (news - 50) * 0.5
            notes.append(f"新闻情绪={news:.2f}")
        if bearish is not None:
            sentiment -= bearish * 20 if 0 <= bearish <= 1 else bearish * 0.2
        sentiment = max(0.0, min(100.0, sentiment))

    return trend, valuation, sentiment, "; ".join(notes[:6])


def collect_market_snapshots(symbols: Iterable[str]) -> list[dict[str, Any]]:
    if not settings.enable_market_data:
        log.info("Market data connectors disabled: ENABLE_MARKET_DATA=false")
        return []
    if not settings.alpha_vantage_api_key and not settings.finnhub_api_key:
        log.info("Market data connectors enabled but no ALPHA_VANTAGE_API_KEY or FINNHUB_API_KEY configured")
        return []

    unique_symbols = []
    seen = set()
    for symbol in symbols:
        s = str(symbol or "").upper().strip()
        if s and s not in seen:
            unique_symbols.append(s)
            seen.add(s)
        if len(unique_symbols) >= settings.market_data_max_symbols:
            break

    rows: list[dict[str, Any]] = []
    for idx, symbol in enumerate(unique_symbols, start=1):
        row: dict[str, Any] = {
            "ticker": symbol,
            "price": None,
            "change_pct": None,
            "volume": None,
            "ret_20d": None,
            "ret_60d": None,
            "sma20": None,
            "sma50": None,
            "week_52_high": None,
            "week_52_low": None,
            "pe_ratio": None,
            "ps_ratio": None,
            "peg_ratio": None,
            "revenue_growth_yoy": None,
            "profit_margin": None,
            "gross_margin": None,
            "net_margin": None,
            "market_cap": None,
            "beta": None,
            "news_buzz": None,
            "news_sentiment_score": None,
            "news_bearish_percent": None,
            "finnhub_insider_buy_count": None,
            "finnhub_insider_sell_count": None,
            "finnhub_insider_buy_amount": None,
            "finnhub_insider_sell_amount": None,
            "trend_score": None,
            "valuation_score": None,
            "sentiment_score": None,
            "data_sources": [],
            "summary_note": "",
        }
        log.info("Market data %s/%s %s", idx, len(unique_symbols), symbol)
        if settings.alpha_vantage_api_key:
            for payload, source in [
                (_alpha_global_quote(symbol), "alpha_quote"),
                (_alpha_daily_technical(symbol), "alpha_daily"),
                (_alpha_overview(symbol), "alpha_overview"),
            ]:
                if payload:
                    row.update({k: v for k, v in payload.items() if v is not None})
                    row["data_sources"].append(source)
        if settings.finnhub_api_key:
            for payload, source in [
                (_finnhub_quote(symbol), "finnhub_quote"),
                (_finnhub_basic_financials(symbol), "finnhub_basic"),
                (_finnhub_news_sentiment(symbol), "finnhub_news"),
                (_finnhub_insider_summary(symbol), "finnhub_insider"),
            ]:
                if payload:
                    row.update({k: v for k, v in payload.items() if v is not None})
                    row["data_sources"].append(source)
        trend, valuation, sentiment, note = _market_quality_scores(row)
        row["trend_score"] = trend
        row["valuation_score"] = valuation
        row["sentiment_score"] = sentiment
        row["summary_note"] = note
        row["data_sources"] = ",".join(row["data_sources"])
        if row["data_sources"]:
            rows.append(row)
    log.info("Market snapshots collected: %s/%s", len(rows), len(unique_symbols))
    return rows


def apply_market_context_to_scores(scores: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not scores or not snapshots:
        return scores
    by_ticker = {str(s.get("ticker") or "").upper(): s for s in snapshots}
    enriched: list[dict[str, Any]] = []
    for row in scores:
        out = dict(row)
        snap = by_ticker.get(str(row.get("ticker") or "").upper())
        if not snap:
            enriched.append(out)
            continue
        trend = _as_float(snap.get("trend_score"))
        valuation = _as_float(snap.get("valuation_score"))
        sentiment = _as_float(snap.get("sentiment_score"))
        adjustment = 0.0
        notes: list[str] = []
        if trend is not None:
            adjustment += (trend - 50.0) * 0.08
            notes.append(f"趋势分={trend:.0f}")
        if valuation is not None:
            adjustment += (valuation - 50.0) * 0.06
            notes.append(f"估值/基本面分={valuation:.0f}")
        if sentiment is not None:
            adjustment += (sentiment - 50.0) * 0.05
            notes.append(f"新闻情绪分={sentiment:.0f}")
        original = float(out.get("opportunity_score") or 0)
        out["opportunity_score"] = round(max(0.0, min(100.0, original + adjustment)), 2)
        if notes:
            note = snap.get("summary_note") or ""
            out["explanation"] = str(out.get("explanation") or "") + " 市场/基本面补充：" + "; ".join(notes) + (f" ({note})" if note else "")
        enriched.append(out)
    return sorted(enriched, key=lambda r: r.get("opportunity_score", 0), reverse=True)
