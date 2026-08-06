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


def _is_structural_primary_transaction(row: Mapping[str, object]) -> bool:
    if is_asset_or_holding_disclosure(row):
        return False
    return _upper(row.get("action")) in PRIMARY_TRANSACTION_ACTIONS


def is_credible_directional_transaction(row: Mapping[str, object]) -> bool:
    """Return True only for trustworthy directional transaction signals.

    Raw rows remain in storage for audit. This filter governs transaction counts,
    rankings, charts, consensus, WIS inputs and AI context.
    """
    if not _is_structural_primary_transaction(row):
        return False

    source = _upper(row.get("source"))
    action = _upper(row.get("action"))
    code = _upper(row.get("transaction_code"))
    amount = _float(row.get("amount_usd"))
    actor = _upper(row.get("whale_name"))
    raw_text = " ".join(str(v or "") for v in _raw(row).values()).upper()

    # Political disclosures use amount ranges; one- and two-digit values are
    # parser artefacts rather than credible disclosed consideration.
    if source.startswith("POLITICAL") and 0 < amount < 100:
        return False

    # Awards, exercises, conversions and derivative-only acquisitions are not
    # open-market directional purchases.
    derivative_markers = r"DERIVATIVE|OPTION|EXERCISE|CONVERSION|AWARD|VEST|RESTRICTED STOCK|RSU"
    if action == "BUY" and (code in {"A", "M", "C", "F", "G"} or re.search(derivative_markers, raw_text)):
        return False

    # Mirrored broker/dealer affiliate filings can create tiny technical BUY and
    # SELL rows, e.g. the NMZ $368/$370 cluster. Keep them in raw evidence only.
    broker_actor = re.search(r"BANK OF AMERICA|MERRILL LYNCH|BROKER|SECURITIES INC", actor)
    if source.startswith("SEC") and broker_actor and 0 < amount < 1_000:
        return False

    return True


def is_primary_transaction(row: Mapping[str, object]) -> bool:
    """Unified V41 definition used by every transaction-based product surface."""
    return is_credible_directional_transaction(row)


def primary_transactions(rows: Iterable[Mapping[str, object]]) -> list[dict]:
    return [dict(row) for row in rows if is_primary_transaction(row)]
