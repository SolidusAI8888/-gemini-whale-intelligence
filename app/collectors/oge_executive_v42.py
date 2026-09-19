from __future__ import annotations

import json
import logging
from typing import Mapping

from app.collectors.oge_asset_candidates import evaluate_oge_asset_candidate
from app.collectors.oge_executive import collect_oge_executive_trades as collect_oge_executive_trades_legacy

log = logging.getLogger(__name__)


def _raw(row: Mapping[str, object]) -> dict:
    value = row.get("raw_json")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or ""))
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _asset_text(row: Mapping[str, object]) -> str:
    raw = _raw(row)
    return str(
        raw.get("asset_name")
        or raw.get("name")
        or raw.get("description")
        or row.get("company_name")
        or row.get("ticker")
        or ""
    )


def _normalize_asset_row(row: Mapping[str, object]) -> dict | None:
    if str(row.get("source") or "").upper() != "OGE_EXECUTIVE_ASSET":
        return dict(row)

    # A document-presence row is not a security holding. Preserve it so the
    # product can distinguish "official filing found" from "nothing filed";
    # downstream holding and concentration builders explicitly exclude OGE-DOC.
    if str(row.get("action") or "").upper() == "DISCLOSURE" and str(row.get("ticker") or "").upper() == "OGE-DOC":
        return dict(row)

    candidate = evaluate_oge_asset_candidate(_asset_text(row))
    if candidate.quality != "accepted" or not candidate.canonical_key:
        log.info(
            "V42 rejected OGE asset before DB upsert: reason=%s raw=%s",
            candidate.rejected_reason,
            candidate.raw_text[:180],
        )
        return None

    normalized = dict(row)
    raw = _raw(row)
    raw["original_asset_name"] = raw.get("asset_name") or row.get("company_name")
    raw["asset_name"] = candidate.asset_name
    raw["canonical_asset_key"] = candidate.canonical_key
    raw["asset_category"] = candidate.category
    raw["v42_quality_gate"] = "accepted"
    normalized["company_name"] = candidate.asset_name
    normalized["raw_json"] = json.dumps(raw, ensure_ascii=False)
    return normalized


def collect_oge_executive_trades(user_agent: str, lookback_days: int) -> list[dict]:
    """V42 OGE collector facade.

    The legacy collector still owns network/PDF parsing. Before any row reaches
    the database, OGE asset disclosures pass through the V42 semantic candidate
    gate. Amount-only, income-type, financing-term and fragment rows are dropped;
    accepted assets are stored under their normalized entity names.
    """
    log.info("V42 OGE collector ACTIVE: starting legacy collection + pre-upsert quality gate")
    rows = collect_oge_executive_trades_legacy(user_agent, lookback_days)
    output: list[dict] = []
    rejected = 0
    accepted_assets = 0
    passthrough_nonassets = 0
    for row in rows:
        is_asset = str(row.get("source") or "").upper() == "OGE_EXECUTIVE_ASSET"
        normalized = _normalize_asset_row(row)
        if normalized is None:
            rejected += 1
            continue
        output.append(normalized)
        if is_asset:
            accepted_assets += 1
        else:
            passthrough_nonassets += 1
    log.info(
        "V42 OGE pre-upsert gate COMPLETE: input=%s output=%s accepted_assets=%s rejected_assets=%s passthrough_nonassets=%s",
        len(rows),
        len(output),
        accepted_assets,
        rejected,
        passthrough_nonassets,
    )
    return output


normalize_oge_asset_row_for_tests = _normalize_asset_row
