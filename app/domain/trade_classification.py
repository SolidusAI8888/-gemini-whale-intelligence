from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import re


PRIMARY_TRANSACTION_ACTIONS = frozenset({"BUY", "SELL", "EXCHANGE"})
ASSET_OR_HOLDING_ACTIONS = frozenset({"HOLDING", "DISCLOSURE", "HOLDING_13F"})
ASSET_OR_HOLDING_SOURCES = frozenset({"OGE_EXECUTIVE_ASSET", "INSTITUTIONAL_13F"})


def _upper(value: object) -> str:
    return str(value or "").strip().upper()


def _float(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _raw(row: Mapping[str, object]) -> dict:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def is_asset_or_holding_disclosure(row: Mapping[str, object]) -> bool:
    source = _upper(row.get("source"))
    action = _upper(row.get("action"))
    return source in ASSET_OR_HOLDING_SOURCES or action in ASSET_OR_HOLDING_ACTIONS


def is_primary_transaction(row: Mapping[str, object]) -> bool:
    """Structural classification: BUY/SELL/EXCHANGE and not a holding disclosure."""
    if is_asset_or_holding_disclosure(row):
        return False
    return _upper(row.get("action")) in PRIMARY_TRANSACTION_ACTIONS


def is_credible_directional_transaction(row: Mapping[str, object]) -> bool:
    """Exclude malformed or technical rows from directional signal products.

    This is deliberately stricter than ``is_primary_transaction``. Raw rows stay
    in the database for audit, but implausible political amounts, derivative-only
    exercises and tiny broker/dealer affiliate Form 4 rows do not enter rankings,
    charts, counts, consensus or AI context.
    """
    if not is_primary_transaction(row):
        return False

    source = _upper(row.get("source"))
    action = _upper(row.get("action"))
    code = _upper(row.get("transaction_code"))
    amount = _float(row.get("amount_usd"))
    actor = _upper(row.get("whale_name"))
    raw = _raw(row)
    raw_text = " ".join(str(v or "") for v in raw.values()).upper()

    # Political disclosures use ranges; single-digit values are parser artefacts.
    if source.startswith("POLITICAL") and 0 < amount < 100:
        return False

    # Option exercise, award, conversion and derivative-only rows are not open-
    # market directional purchases even if an upstream normalizer labelled BUY.
    derivative_markers = r"DERIVATIVE|OPTION|EXERCISE|CONVERSION|AWARD|VEST|RESTRICTED STOCK|RSU"
    if action == "BUY" and (code in {"A", "M", "C", "F", "G"} or re.search(derivative_markers, raw_text)):
        return False

    # Broker/dealer affiliates frequently file mirrored or technical Form 4 rows.
    # Tiny values such as NMZ $368 are retained in raw evidence but excluded from
    # the active-buy signal and all downstream directional summaries.
    broker_actor = re.search(r"BANK OF AMERICA|MERRILL LYNCH|BROKER|SECURITIES INC", actor)
    if action == "BUY" and source.startswith("SEC") and broker_actor and 0 < amount < 1_000:
        return False

    return True


def primary_transactions(rows: Iterable[Mapping[str, object]]) -> list[dict]:
    """Materialize credible directional transaction rows as dictionaries."""
    return [dict(row) for row in rows if is_credible_directional_transaction(row)]
