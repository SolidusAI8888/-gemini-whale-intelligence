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
    sec_user_agent: str = os.getenv("SEC_USER_AGENT", "GeminiWhaleIntelligence contact@example.com")
    lookback_days: int = _int("LOOKBACK_DAYS", 3)
    max_companies: int = _int("MAX_COMPANIES", 0)  # 0 = all companies in universe
    min_opportunity_score: float = _float("MIN_OPPORTUNITY_SCORE", 55.0)
    dry_run: bool = _bool("DRY_RUN", True)
    send_email: bool = _bool("SEND_EMAIL", False)
    enable_gemini: bool = _bool("ENABLE_GEMINI", False)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "")
    email_to: str = os.getenv("EMAIL_TO", "")


settings = Settings()
