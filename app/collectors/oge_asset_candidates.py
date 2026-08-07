from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable

from app.domain.asset_semantics import parse_oge_asset_semantics


@dataclass(frozen=True)
class OgeAssetCandidate:
    raw_text: str
    asset_name: str
    canonical_key: str
    category: str
    amount_text: str | None
    quality: str
    rejected_reason: str | None = None


_AMOUNT_RE = re.compile(
    r"(?:over|greater than|more than)?\s*\$[0-9][0-9,]*(?:\.\d+)?"
    r"(?:\s*[–—-]\s*\$?[0-9][0-9,]*(?:\.\d+)?)?",
    re.I,
)


def _collapse(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def evaluate_oge_asset_candidate(value: object) -> OgeAssetCandidate:
    raw = _collapse(value)
    parsed = parse_oge_asset_semantics(raw)
    return OgeAssetCandidate(
        raw_text=raw,
        asset_name=parsed.asset_name,
        canonical_key=parsed.canonical_key,
        category=parsed.category,
        amount_text=parsed.amount_text,
        quality=parsed.quality,
        rejected_reason=parsed.rejected_reason,
    )


def extract_oge_asset_candidates(lines: Iterable[str], *, max_window: int = 3) -> list[OgeAssetCandidate]:
    """Extract only semantic asset entities from OGE PDF text lines.

    V42 quality gate: amount-only cells, income-type cells, financing terms,
    footnotes and OCR/table fragments never become database candidates.
    Multi-line windows are considered only when the first line is not already a
    valid asset and the combined window produces a valid canonical entity.
    """
    cleaned = [_collapse(line) for line in lines]
    cleaned = [line for line in cleaned if line]

    accepted: dict[str, OgeAssetCandidate] = {}
    for idx, line in enumerate(cleaned):
        single = evaluate_oge_asset_candidate(line)
        if single.quality == "accepted" and single.canonical_key and _AMOUNT_RE.search(line):
            accepted.setdefault(single.canonical_key, single)
            continue

        # Only repair rows that appear split across adjacent PDF extraction lines.
        for width in range(2, max(2, int(max_window)) + 1):
            window_lines = cleaned[idx : idx + width]
            if len(window_lines) < width:
                break
            window = " ".join(window_lines)
            if not _AMOUNT_RE.search(window):
                continue
            candidate = evaluate_oge_asset_candidate(window)
            if candidate.quality != "accepted" or not candidate.canonical_key:
                continue
            accepted.setdefault(candidate.canonical_key, candidate)
            break

    return list(accepted.values())
