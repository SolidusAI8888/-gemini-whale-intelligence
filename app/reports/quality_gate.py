from __future__ import annotations

import os
import re
from typing import Iterable, Mapping

from app.domain.trade_classification import is_primary_transaction


class ReportQualityError(RuntimeError):
    pass


KEY_POLITICAL_REGRESSION_TICKERS = ("UBER", "MSFT", "INTC")
KEY_POLITICAL_LARGE_BUY_USD = 250_000.0


def _cabinet_section(html: str) -> str:
    match = re.search(
        r'<section id="v40-cabinet-oge-radar">(.*?)</section>',
        html or "",
        re.I | re.S,
    )
    return match.group(1) if match else ""


def _active_buy_section(html: str) -> str:
    match = re.search(
        r'<section id="v40-active-buy-radar">(.*?)</section>',
        html or "",
        re.I | re.S,
    )
    return match.group(1) if match else ""


def _build_sha() -> str:
    return str(os.getenv("REPORT_BUILD_SHA") or os.getenv("GITHUB_SHA") or "local")[:12]


def _parse_billions(label: str) -> float | None:
    match = re.fullmatch(r"\$([0-9][0-9,]*(?:\.\d+)?)B", label.strip(), re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def _is_political(row: Mapping[str, object]) -> bool:
    source = str(row.get("source") or "").upper()
    category = str(row.get("whale_category") or "").upper()
    return source.startswith("POLITICAL") or category.startswith("POLITICAL")


def validate_key_political_visibility(
    html: str,
    rows: Iterable[Mapping[str, object]],
    *,
    min_large_buy_usd: float = KEY_POLITICAL_LARGE_BUY_USD,
) -> None:
    """Fail closed if known large Congress BUYs survive classification but vanish from HTML.

    This is deliberately conditional on the data actually present in the formal
    report input.  It therefore does not fabricate or require a historical
    transaction that is absent from the database.  If a key ticker has at least
    one accepted political BUY >= ``min_large_buy_usd``, however, the final
    active-buy radar must display that ticker.  V46 was introduced after valid
    UBER/MSFT/INTC records existed in SQLite but were silently lost by a smaller
    report re-fetch limit.
    """
    active = _active_buy_section(html)
    build = _build_sha()
    largest_by_ticker: dict[str, float] = {ticker: 0.0 for ticker in KEY_POLITICAL_REGRESSION_TICKERS}

    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker not in largest_by_ticker:
            continue
        if not _is_political(row):
            continue
        if str(row.get("action") or "").strip().upper() != "BUY":
            continue
        if not is_primary_transaction(row):
            continue
        try:
            amount = float(row.get("amount_usd") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        largest_by_ticker[ticker] = max(largest_by_ticker[ticker], amount)

    missing: list[str] = []
    for ticker, largest in largest_by_ticker.items():
        if largest < min_large_buy_usd:
            continue
        if not re.search(rf"<b>\s*{re.escape(ticker)}\s*</b>", active, re.I):
            missing.append(f"{ticker} largest=${largest:,.0f}")

    if missing:
        raise ReportQualityError(
            "Political large-BUY visibility regression "
            f"(build={build}): " + "; ".join(missing)
        )


def validate_report_html(html: str) -> None:
    """Fail closed before report release when known report regressions return."""
    build = _build_sha()
    if not html or "Gemini-美股聪明钱_政商巨鲸行动追踪" not in html:
        raise ReportQualityError(f"Report HTML is empty or missing the expected title (build={build})")

    cabinet = _cabinet_section(html)
    forbidden_oge_assets = [
        r"<b>\s*Over\s+\$",
        r"<b>\s*Dividends?\b",
        r"<b>\s*Crop Sales\b",
        r"<b>\s*Interest(?: Income)?\b",
        r"<b>\s*RATE TERM\b",
        r"<b>\s*On Demand\b",
        r"<b>\s*#?\s*EMPLOYER OR PARTY\b",
        r"<b>[^<]*\bLLC\s*,\s*co\b",
        r"<b>\s*\(?\s*or less\b",
    ]
    for pattern in forbidden_oge_assets:
        if re.search(pattern, cabinet, re.I):
            raise ReportQualityError(f"OGE semantic quality gate failed (build={build}): {pattern}")

    header = re.search(r"今日新增/变化可信记录：\s*(\d+)\s*条", html)
    overview = re.search(r"本次新增可信记录\s*(\d+)\s*条", html)
    if header and overview and header.group(1) != overview.group(1):
        raise ReportQualityError(
            f"New-record count mismatch (build={build}): header={header.group(1)} overview={overview.group(1)}"
        )

    for label in re.findall(r"\$[0-9][0-9,]*(?:\.\d+)?B", html):
        billions = _parse_billions(label)
        if billions is not None and billions > 5_000:
            raise ReportQualityError(f"13F/holding amount exceeds $5T sanity limit (build={build}): {label}")


validate_report_html_for_tests = validate_report_html
validate_key_political_visibility_for_tests = validate_key_political_visibility
cabinet_section_for_tests = _cabinet_section
active_buy_section_for_tests = _active_buy_section
