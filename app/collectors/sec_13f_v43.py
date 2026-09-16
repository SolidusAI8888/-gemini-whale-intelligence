from __future__ import annotations

import json
import logging
from typing import Mapping

from app.collectors.sec_13f import (
    collect_institutional_13f_holdings as collect_institutional_13f_holdings_legacy,
    get_institutional_13f_status,
)

log = logging.getLogger(__name__)


def _raw(row: Mapping[str, object]) -> dict:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _normalize_13f_row(row: Mapping[str, object]) -> dict:
    normalized = dict(row)
    raw = _raw(row)
    reported = raw.get("value_reported")
    if reported is None:
        reported = raw.get("value_dollars")
    if reported is None:
        return normalized

    try:
        reported_value = float(str(reported).replace(",", ""))
    except (TypeError, ValueError):
        return normalized

    # Since 2023-01-03 Form 13F values are reported to the nearest U.S. dollar.
    # Treat the raw XML <value> as dollars for modern filings; do not multiply by 1000.
    report_date = str(raw.get("report_period") or row.get("trade_date") or "")[:10]
    if report_date >= "2023-01-03":
        normalized["amount_usd"] = reported_value
        raw["value_unit"] = "usd"
        raw["value_dollars"] = reported_value
        raw.pop("value_thousands_usd", None)
        raw["v43_13f_unit_normalized"] = True
        normalized["raw_json"] = json.dumps(raw, ensure_ascii=False)
    return normalized


def collect_institutional_13f_holdings(user_agent: str, lookback_days: int = 370) -> list[dict]:
    rows = collect_institutional_13f_holdings_legacy(user_agent, lookback_days)
    normalized = [_normalize_13f_row(row) for row in rows]
    changed = sum(1 for before, after in zip(rows, normalized) if before.get("amount_usd") != after.get("amount_usd"))
    log.info("V43 13F dollar normalization: input=%s corrected=%s", len(rows), changed)
    return normalized


normalize_13f_row_for_tests = _normalize_13f_row
