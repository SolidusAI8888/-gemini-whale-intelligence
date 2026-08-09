from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import logging
from typing import Iterable

import pandas as pd
import requests

log = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Wikipedia rejects some default urllib/pandas requests from hosted runners. Fetch
# the page ourselves with a normal browser UA, then let pandas parse the returned
# HTML. Minimum-size guards stop a partial/changed page from silently becoming the
# production trading universe.
INDEX_HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GeminiWhaleUniverse/1.0; +https://github.com/SolidusAI8888/-gemini-whale-intelligence)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.8",
}
SP500_MIN_COMPONENTS = 480
NASDAQ100_MIN_COMPONENTS = 95

# Emergency fallback only. A fallback universe is deliberately loud in logs and
# must never be mistaken for successful S&P 500 + Nasdaq-100 coverage.
FALLBACK_TICKERS = {
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "AVGO", "TSLA",
    "COST", "NFLX", "AMD", "ADBE", "PEP", "CSCO", "TMUS", "INTU", "QCOM",
    "AMGN", "TXN", "INTC", "AMAT", "ISRG", "BKNG", "HON", "CMCSA", "PANW",
    "VRTX", "MU", "LRCX", "ADP", "ADI", "SBUX", "GILD", "MDLZ", "MELI",
    "KLAC", "REGN", "SNPS", "CDNS", "PYPL", "MAR", "ORLY", "CRWD", "ASML",
    "LIN", "LLY", "JPM", "V", "MA", "UNH", "XOM", "JNJ", "PG", "HD", "MRK",
    "ABBV", "CRM", "CVX", "BAC", "KO", "WMT", "DIS", "MCD", "TMO", "ACN",
}


@dataclass(frozen=True)
class UniverseCompany:
    ticker: str
    cik: str
    title: str
    source_index: str


def normalize_ticker(ticker: str) -> str:
    return ticker.strip().upper().replace(".", "-")


def _read_html_tables(url: str) -> list[pd.DataFrame]:
    response = requests.get(url, headers=INDEX_HTTP_HEADERS, timeout=30)
    response.raise_for_status()
    return pd.read_html(StringIO(response.text))


def _read_sp500() -> set[str]:
    tables = _read_html_tables(SP500_URL)
    table = tables[0]
    col = "Symbol" if "Symbol" in table.columns else table.columns[0]
    tickers = {normalize_ticker(x) for x in table[col].dropna().astype(str)}
    if len(tickers) < SP500_MIN_COMPONENTS:
        raise RuntimeError(f"S&P 500 page parsed only {len(tickers)} tickers; refusing partial universe")
    return tickers


def _read_nasdaq100() -> set[str]:
    tables = _read_html_tables(NASDAQ100_URL)
    candidates: list[pd.DataFrame] = []
    for table in tables:
        columns = {str(c).lower(): c for c in table.columns}
        if "ticker" in columns or "symbol" in columns:
            candidates.append(table)
    if not candidates:
        raise RuntimeError("Nasdaq-100 page contained no ticker/symbol table")
    table = max(candidates, key=len)
    column = None
    for c in table.columns:
        if str(c).lower() in {"ticker", "symbol"}:
            column = c
            break
    if column is None:
        raise RuntimeError("Nasdaq-100 table contained no ticker/symbol column")
    tickers = {normalize_ticker(x) for x in table[column].dropna().astype(str)}
    if len(tickers) < NASDAQ100_MIN_COMPONENTS:
        raise RuntimeError(f"Nasdaq-100 page parsed only {len(tickers)} tickers; refusing partial universe")
    return tickers


def load_universe_tickers() -> set[str]:
    sp500: set[str] = set()
    nasdaq100: set[str] = set()
    try:
        sp500 = _read_sp500()
        log.info("Loaded %s S&P 500 tickers", len(sp500))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load S&P 500 universe: %s", exc)
    try:
        nasdaq100 = _read_nasdaq100()
        log.info("Loaded %s Nasdaq-100 tickers", len(nasdaq100))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load Nasdaq-100 universe: %s", exc)

    # The project contract is the union of both indices. If either source fails,
    # do not silently claim that the surviving index is the complete universe.
    if not sp500 or not nasdaq100:
        missing = []
        if not sp500:
            missing.append("S&P 500")
        if not nasdaq100:
            missing.append("Nasdaq-100")
        log.error(
            "Incomplete target universe (%s unavailable); using emergency fallback of %s tickers",
            ", ".join(missing),
            len(FALLBACK_TICKERS),
        )
        return set(FALLBACK_TICKERS)

    tickers = sp500 | nasdaq100
    log.info(
        "Full index universe loaded: sp500=%s nasdaq100=%s union=%s",
        len(sp500),
        len(nasdaq100),
        len(tickers),
    )
    return tickers


def fetch_sec_company_tickers(user_agent: str) -> dict[str, dict]:
    headers = {"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate", "Host": "www.sec.gov"}
    response = requests.get(SEC_TICKERS_URL, headers=headers, timeout=30)
    response.raise_for_status()
    raw = response.json()
    result: dict[str, dict] = {}
    for item in raw.values():
        ticker = normalize_ticker(item["ticker"])
        result[ticker] = {
            "ticker": ticker,
            "cik": str(item["cik_str"]).zfill(10),
            "title": item.get("title", ""),
        }
    return result


def build_company_universe(user_agent: str, max_companies: int = 0) -> list[UniverseCompany]:
    target = load_universe_tickers()
    sec_map = fetch_sec_company_tickers(user_agent)
    companies: list[UniverseCompany] = []
    for ticker in sorted(target):
        if ticker in sec_map:
            item = sec_map[ticker]
            companies.append(
                UniverseCompany(
                    ticker=ticker,
                    cik=item["cik"],
                    title=item["title"],
                    source_index="SP500_OR_NASDAQ100",
                )
            )
        else:
            log.debug("Ticker %s not found in SEC company ticker map", ticker)
    if max_companies > 0:
        companies = companies[:max_companies]
    log.info("Company universe ready: %s companies", len(companies))
    return companies


def tickers_from_companies(companies: Iterable[UniverseCompany]) -> set[str]:
    return {company.ticker for company in companies}
