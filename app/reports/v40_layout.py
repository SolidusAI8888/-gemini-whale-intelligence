from __future__ import annotations

import re
from typing import Iterable, Mapping

from app.reports.v40_oge import build_cabinet_oge_radar
from app.reports.v40_report import apply_v40_report_layout


def apply_v40_full_layout(
    html: str,
    primary_rows: Iterable[Mapping[str, object]],
    oge_rows: Iterable[Mapping[str, object]],
    *,
    new_since: str | None = None,
) -> str:
    """Apply the complete V40 report overlay in a stable order."""

    updated = apply_v40_report_layout(html, primary_rows, new_since=new_since)
    oge_radar = build_cabinet_oge_radar(oge_rows, new_since=new_since)

    active_end = re.search(r"</section>", updated, re.I)
    if active_end:
        insert_at = active_end.end()
        return updated[:insert_at] + oge_radar + updated[insert_at:]

    first_h2 = re.search(r"<h2\b", updated, re.I)
    if first_h2:
        return updated[: first_h2.start()] + oge_radar + updated[first_h2.start() :]

    body_end = re.search(r"</body>", updated, re.I)
    if body_end:
        return updated[: body_end.start()] + oge_radar + updated[body_end.start() :]
    return updated + oge_radar
