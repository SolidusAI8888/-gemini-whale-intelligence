from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Iterable

import pandas as pd
import requests

log = logging.getLogger(__name__)

SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
NASDAQ100_URL = "https://en.wikipedia.org/wiki/Nasdaq-100"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Fallback keeps the MVP runnable even when Wikipedia/SEC is temporarily unavailable.
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


def _read_sp500() -> set[str]:
    tables = pd.read_html(SP500_URL)
    table = tables[0]
    col = "Symbol" if "Symbol" in table.columns else table.columns[0]
    return {normalize_ticker(x) for x in table[col].dropna().astype(str)}


def _read_nasdaq100() -> set[str]:
    tables = pd.read_html(NASDAQ100_URL)
    candidates: list[pd.DataFrame] = []
    for table in tables:
        columns = {str(c).lower(): c for c in table.columns}
        if "ticker" in columns or "symbol" in columns:
            candidates.append(table)
    if not candidates:
        return set()
    table = max(candidates, key=len)
    column = None
    for c in table.columns:
        if str(c).lower() in {"ticker", "symbol"}:
            column = c
            break
    if column is None:
        return set()
    return {normalize_ticker(x) for x in table[column].dropna().astype(str)}


def load_universe_tickers() -> set[str]:
    tickers: set[str] = set()
    try:
        tickers |= _read_sp500()
        log.info("Loaded %s S&P 500 tickers", len(tickers))
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load S&P 500 universe: %s", exc)
    try:
        before = len(tickers)
        tickers |= _read_nasdaq100()
        log.info("Loaded %s Nasdaq-100 tickers", len(tickers) - before)
    except Exception as exc:  # noqa: BLE001
        log.warning("Failed to load Nasdaq-100 universe: %s", exc)

    if not tickers:
        log.warning("Using fallback universe of %s tickers", len(FALLBACK_TICKERS))
        tickers = set(FALLBACK_TICKERS)
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
