from __future__ import annotations

import re

from app.collectors.oge_executive_v42 import collect_oge_executive_trades
from app.collectors.sec_13f_v43 import collect_institutional_13f_holdings
from app.config import settings
from app.reports.quality_gate import validate_report_html
from app.reports.v40_oge import build_cabinet_oge_radar


def main() -> None:
    oge_rows = collect_oge_executive_trades(settings.sec_user_agent, 370)
    institutional_rows = collect_institutional_13f_holdings(settings.sec_user_agent, 370)

    oge_assets = [row for row in oge_rows if str(row.get("source") or "").upper() == "OGE_EXECUTIVE_ASSET"]
    if not oge_assets:
        raise RuntimeError("Live smoke: no OGE asset rows survived V42 gate")
    if not institutional_rows:
        raise RuntimeError("Live smoke: no 13F holdings parsed from SEC")

    max_13f = max(float(row.get("amount_usd") or 0) for row in institutional_rows)
    if max_13f > 5_000_000_000_000:
        raise RuntimeError(f"Live smoke: implausible 13F holding amount {max_13f:.0f}")

    cabinet = build_cabinet_oge_radar(oge_assets, limit=50)
    html = (
        '<!doctype html><html><body>'
        '<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>'
        + cabinet
        + '<h2>Live 13F sanity</h2>'
        + ''.join(f'<p>${float(row.get("amount_usd") or 0) / 1_000_000_000:.2f}B</p>' for row in institutional_rows[:20])
        + '</body></html>'
    )
    validate_report_html(html)

    forbidden = [
        r'<b>\s*Over\s+\$', r'<b>\s*Dividends?\b', r'<b>\s*Crop Sales\b',
        r'<b>\s*Interest(?: Income)?\b', r'<b>\s*RATE TERM\b', r'<b>\s*On Demand\b',
        r'<b>\s*#?\s*EMPLOYER OR PARTY\b', r'<b>[^<]*\bLLC\s*,\s*co\b',
    ]
    for pattern in forbidden:
        if re.search(pattern, cabinet, re.I):
            raise RuntimeError(f"Live smoke: forbidden OGE asset survived: {pattern}")

    print(
        "V43 live release smoke PASS",
        f"oge_assets={len(oge_assets)}",
        f"13f_rows={len(institutional_rows)}",
        f"max_13f_usd={max_13f:.0f}",
    )


if __name__ == "__main__":
    main()
