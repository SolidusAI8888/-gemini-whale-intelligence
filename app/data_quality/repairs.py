from __future__ import annotations

import json

from app.db import get_conn


def normalize_institutional_13f_amounts() -> int:
    """Repair persisted modern 13F rows to dollar units.

    For report periods on/after 2023-01-03, SEC Form 13F values are reported in
    dollars, not thousands. Recalculate amount_usd from raw_json.value_reported.
    Legacy pre-2023 rows retain their historical unit behavior.
    """
    repaired = 0
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, amount_usd, trade_date, raw_json
            FROM trades
            WHERE source = 'INSTITUTIONAL_13F'
            """
        ).fetchall()
        for row in rows:
            try:
                raw = json.loads(row["raw_json"] or "{}")
            except Exception:
                continue
            reported = raw.get("value_reported")
            if reported is None:
                continue
            try:
                reported_value = float(str(reported).replace(",", ""))
            except (TypeError, ValueError):
                continue
            report_date = str(raw.get("report_period") or row["trade_date"] or "")[:10]
            if report_date < "2023-01-03":
                continue
            current = float(row["amount_usd"] or 0)
            expected = reported_value
            if expected <= 0:
                continue
            if abs(current - expected) <= max(1.0, expected * 0.000001):
                continue
            raw["value_unit"] = "usd"
            raw["value_dollars"] = reported_value
            raw.pop("value_thousands_usd", None)
            raw["v43_13f_unit_normalized"] = True
            conn.execute(
                "UPDATE trades SET amount_usd = ?, raw_json = ? WHERE id = ?",
                (expected, json.dumps(raw, ensure_ascii=False), row["id"]),
            )
            repaired += 1
        conn.commit()
    return repaired
