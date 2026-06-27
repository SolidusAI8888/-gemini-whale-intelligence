from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_path: Path = Path(os.getenv("DATABASE_PATH", "data/whale.db"))
    report_dir: Path = Path(os.getenv("REPORT_DIR", "data/reports"))
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "WhaleIntelligenceGemini contact@example.com")
    lookback_days: int = _int("LOOKBACK_DAYS", 3)
    max_companies: int = _int("MAX_COMPANIES", 0)  # 0 = all companies in universe
    min_opportunity_score: float = _float("MIN_OPPORTUNITY_SCORE", 55.0)

    # Formal report scan window.  V18 report excludes trade dates before this date
    # so older 2025 records do not dominate the daily brief.
    scan_start_date: str = os.getenv("SCAN_START_DATE", "2026-01-01")
    dry_run: bool = _bool("DRY_RUN", True)
    send_email: bool = _bool("SEND_EMAIL", False)
    enable_gemini: bool = _bool("ENABLE_GEMINI", True)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")

    # Political whale module. Default provider "auto" uses the official House Clerk
    # ZIP archive and, when FMP_API_KEY is supplied, optional FMP House/Senate endpoints.
    enable_political_trades: bool = _bool("ENABLE_POLITICAL_TRADES", True)
    political_provider: str = os.getenv("POLITICAL_PROVIDER", "auto")  # auto|official_house|fmp
    political_max_filings: int = _int("POLITICAL_MAX_FILINGS", 300)
    fmp_api_key: str = os.getenv("FMP_API_KEY", "")
    # FMP congressional House/Senate endpoints are paid/restricted for many keys.
    # Keep them off by default so the free setup relies on official House disclosures
    # and does not spam 402 Payment Required warnings. Turn on only after upgrading FMP.
    fmp_congressional_enabled: bool = _bool("FMP_CONGRESSIONAL_ENABLED", False)
    fmp_max_pages: int = _int("FMP_MAX_PAGES", 5)
    fmp_page_limit: int = _int("FMP_PAGE_LIMIT", 100)
    # Comma-separated FMP congressional endpoints. FMP has both latest-disclosure
    # endpoints and symbol/name activity endpoints; use all by default for better recall.
    fmp_house_endpoints: str = os.getenv("FMP_HOUSE_ENDPOINTS", "house-latest,house-trades")
    fmp_senate_endpoints: str = os.getenv("FMP_SENATE_ENDPOINTS", "senate-latest,senate-trades")
    # Names to query via FMP by-name endpoints. Useful for Pelosi/Trump/other watchlist figures
    # whose trades may be outside the core S&P500/Nasdaq100 universe or reported as options.
    political_watch_names: str = os.getenv("POLITICAL_WATCH_NAMES", "Pelosi,Trump")
    # Political universe scope:
    #   core = keep only S&P 500 + Nasdaq-100 tickers for political trades
    #   all  = collect political trades even when ticker is outside the core universe
    #   both = same as all, useful for diagnostics while report can show all political records
    political_universe_scope: str = os.getenv("POLITICAL_UNIVERSE_SCOPE", "core").lower().strip()


    # OGE Executive Branch disclosures. This is separate from House/Senate PTR.
    # Configure official OGE/OGE-hosted PDF URLs. Trump gets a dedicated report
    # section; cabinet reports use entries formatted as Name|Title|PDF_URL|Agency.
    enable_oge_executive_trades: bool = _bool("ENABLE_OGE_EXECUTIVE_TRADES", True)
    oge_trump_report_urls: str = os.getenv("OGE_TRUMP_REPORT_URLS", "")
    oge_trump_filer_name: str = os.getenv("OGE_TRUMP_FILER_NAME", "Donald J. Trump")
    oge_cabinet_reports: str = os.getenv("OGE_CABINET_REPORTS", "")
    oge_max_reports: int = _int("OGE_MAX_REPORTS", 20)
    oge_executive_watchlist: str = os.getenv("OGE_EXECUTIVE_WATCHLIST", "Donald J. Trump,JD Vance,Marco Rubio,Scott Bessent,Pete Hegseth,Pamela Bondi,Doug Burgum,Brooke Rollins,Howard Lutnick,Lori Chavez-DeRemer,Robert F. Kennedy Jr.,Scott Turner,Sean Duffy,Chris Wright,Linda McMahon,Doug Collins,Kristi Noem,Tulsi Gabbard,Jamieson Greer,Russell Vought,Lee Zeldin,John Ratcliffe,Kelly Loeffler,SEC Chair,FTC Chair")
    # Optional OGE watcher. It scrapes configured public OGE/search-result pages for
    # direct PDF links containing 278T / Transaction and known watchlist names, then
    # feeds those PDFs into the same parser. Keep manual URLs as the primary reliable path.
    enable_oge_auto_discovery: bool = _bool("ENABLE_OGE_AUTO_DISCOVERY", True)
    oge_discovery_urls: str = os.getenv("OGE_DISCOVERY_URLS", "https://www.oge.gov/web/oge.nsf/Officials%20Individual%20Disclosures%20Search%20Collection?OpenForm")
    oge_discovery_watchlist: str = os.getenv("OGE_DISCOVERY_WATCHLIST", os.getenv("OGE_EXECUTIVE_WATCHLIST", "Donald J. Trump,JD Vance,Marco Rubio,Scott Bessent,Pete Hegseth,Pamela Bondi,Doug Burgum,Brooke Rollins,Howard Lutnick,Chris Wright,Doug Collins,Kristi Noem,Tulsi Gabbard,John Ratcliffe"))
    oge_discovery_max_links: int = _int("OGE_DISCOVERY_MAX_LINKS", 50)
    # V19: optionally seed a small set of official OGE Cabinet/Cabinet-level
    # disclosure URLs that are difficult to discover from the generic OGE search
    # landing page.  Users can override/append with OGE_CABINET_REPORTS.
    oge_seed_cabinet_reports_enabled: bool = _bool("OGE_SEED_CABINET_REPORTS_ENABLED", True)
    oge_seed_cabinet_reports: str = os.getenv("OGE_SEED_CABINET_REPORTS", "")
    enable_oge_asset_disclosures: bool = _bool("ENABLE_OGE_ASSET_DISCLOSURES", True)


    # Free market-data connectors. These do not replace political disclosures;
    # they add price, trend, basic fundamentals, news sentiment and independent
    # insider/13F-adjacent checks to make the report less dependent on trades alone.
    enable_market_data: bool = _bool("ENABLE_MARKET_DATA", True)
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
    market_data_max_symbols: int = _int("MARKET_DATA_MAX_SYMBOLS", 25)
    alpha_daily_enabled: bool = _bool("ALPHA_DAILY_ENABLED", True)
    alpha_overview_enabled: bool = _bool("ALPHA_OVERVIEW_ENABLED", True)
    finnhub_basic_financials_enabled: bool = _bool("FINNHUB_BASIC_FINANCIALS_ENABLED", True)
    finnhub_news_enabled: bool = _bool("FINNHUB_NEWS_ENABLED", True)
    finnhub_insider_enabled: bool = _bool("FINNHUB_INSIDER_ENABLED", True)


settings = Settings()
