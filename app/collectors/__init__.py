"""Collector package bootstrap fixes shared by scheduled and preview runs."""

from __future__ import annotations

from collections.abc import Iterable


def _quality_13f_info_table_picker(files: Iterable[str]) -> str | None:
    """Choose the actual 13F holdings table, not the primary cover XML.

    SEC filing directories often contain both a primary 13F-HR cover document
    and a separate information-table XML. Older ranking treated generic
    ``form13f`` names as highly as ``infotable`` and could parse the cover file,
    yielding zero holdings. This picker strongly prefers explicit information
    table names and rejects cover/schema/style documents.
    """
    candidates: list[tuple[int, str]] = []
    for url in files:
        name = url.rsplit("/", 1)[-1].lower()
        if not name.endswith((".xml", ".txt")):
            continue
        if any(token in name for token in ("xsl", "schema", "primary_doc", "cover", "header")):
            continue
        score = 0
        compact = name.replace("_", "").replace("-", "")
        if "informationtable" in compact or "infotable" in compact:
            score += 100
        elif "holdings" in compact or "positions" in compact:
            score += 70
        elif "form13f" in compact:
            score += 10
        if name.endswith(".xml"):
            score += 5
        candidates.append((score, url))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, best_url = candidates[0]
    # A generic XML with no information-table hint is more likely the cover form.
    return best_url if best_score >= 70 else None


# Import and patch once at package initialization. All later imports of
# app.collectors.sec_13f, including app.main, receive the corrected picker.
from app.collectors import sec_13f as _sec_13f  # noqa: E402

_sec_13f._pick_info_table = _quality_13f_info_table_picker

__all__ = ["_quality_13f_info_table_picker"]
