from __future__ import annotations

from collections.abc import Iterable, Mapping


PRIMARY_TRANSACTION_ACTIONS = frozenset({"BUY", "SELL", "EXCHANGE"})
ASSET_OR_HOLDING_ACTIONS = frozenset({"HOLDING", "DISCLOSURE", "HOLDING_13F"})
ASSET_OR_HOLDING_SOURCES = frozenset({"OGE_EXECUTIVE_ASSET", "INSTITUTIONAL_13F"})


def _upper(value: object) -> str:
    return str(value or "").strip().upper()


def is_asset_or_holding_disclosure(row: Mapping[str, object]) -> bool:
    """Return True for disclosures that are not primary market transactions.

    V40 keeps executive asset disclosures and institutional 13F holdings in
    dedicated report sections. They must not inflate transaction counts, BUY/
    SELL rankings, consensus calculations, or transaction-based WIS pillars.
    """

    source = _upper(row.get("source"))
    action = _upper(row.get("action"))
    return source in ASSET_OR_HOLDING_SOURCES or action in ASSET_OR_HOLDING_ACTIONS


def is_primary_transaction(row: Mapping[str, object]) -> bool:
    """Return True only for actionable BUY/SELL/EXCHANGE transaction rows."""

    if is_asset_or_holding_disclosure(row):
        return False
    return _upper(row.get("action")) in PRIMARY_TRANSACTION_ACTIONS


def primary_transactions(rows: Iterable[Mapping[str, object]]) -> list[dict]:
    """Materialize only genuine transaction rows as mutable dictionaries."""

    return [dict(row) for row in rows if is_primary_transaction(row)]
