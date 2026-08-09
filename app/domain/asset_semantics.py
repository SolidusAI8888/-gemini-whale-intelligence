from __future__ import annotations

from dataclasses import dataclass
import re

from app.domain.asset_quality import normalize_oge_asset


@dataclass(frozen=True)
class ParsedAssetSemantic:
    asset_name: str
    canonical_key: str
    category: str
    amount_text: str | None
    income_type: str | None
    financing_term: str | None
    quality: str
    rejected_reason: str | None = None


INCOME_PREFIX_RE = re.compile(
    r"^(dividends?|interest(?: income)?|capital gains?|rent or royalties|rental income|"
    r"crop sales|net distributive income)\b",
    re.I,
)
FINANCING_RE = re.compile(
    r"\b(secured facility|on demand|rate term|government guaranteed collateral|borrower)\b",
    re.I,
)
AMOUNT_ONLY_RE = re.compile(
    r"^(?:over|greater than|more than)?\s*\$?[0-9][0-9,]*(?:\.\d+)?"
    r"(?:\s*[–—-]\s*\$?[0-9][0-9,]*(?:\.\d+)?)?$",
    re.I,
)
TABLE_HEADER_RE = re.compile(
    r"^(?:\s*(?:#|\d+(?:\.\d+)*)?\s*)?(?:"
    r"employer or party\b|city,?\s*state\b|status and terms\b|assets? and income\b|"
    r"source of income\b|type of income\b|income amount\b|value\b|description\b|"
    r"date\b|transaction date\b|notification date\b|amount of transaction\b)",
    re.I,
)


def _strip_empty_prefixes(text: str) -> str:
    """Remove OGE/OCR empty-cell markers before semantic type detection."""
    return re.sub(r"^(?:(?:N/?A|NONE|NOT APPLICABLE)\s+)+", "", text, flags=re.I).strip()


def parse_oge_asset_semantics(value: object) -> ParsedAssetSemantic:
    raw = re.sub(r"\s+", " ", str(value or "")).strip()
    if not raw:
        return ParsedAssetSemantic("", "", "其他资产", None, None, None, "rejected", "empty")

    # Structural labels often arrive with an empty preceding table cell, e.g.
    # "N/A # EMPLOYER OR PARTY ...". Strip those empty-cell markers before
    # deciding whether the row is a header; otherwise the header can be mistaken
    # for an asset and persist into the database/report.
    semantic_probe = _strip_empty_prefixes(raw)
    if TABLE_HEADER_RE.search(semantic_probe):
        return ParsedAssetSemantic("", "", "其他资产", None, None, None, "rejected", "table_header")

    amount = re.search(
        r"(?:over\s+)?\$[0-9][0-9,]*(?:\.\d+)?"
        r"(?:\s*[–—-]\s*\$?[0-9][0-9,]*(?:\.\d+)?)?",
        raw,
        re.I,
    )
    income = INCOME_PREFIX_RE.search(semantic_probe)
    financing = FINANCING_RE.search(semantic_probe)

    stripped = semantic_probe
    if income:
        stripped = ""
    if AMOUNT_ONLY_RE.fullmatch(stripped or raw):
        stripped = ""
    stripped = FINANCING_RE.sub(" ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -:;,|")

    if not stripped:
        reason = "income_type" if income else (
            "amount_only" if AMOUNT_ONLY_RE.fullmatch(raw) else "financing_term"
        )
        return ParsedAssetSemantic(
            "",
            "",
            "其他资产",
            amount.group(0) if amount else None,
            income.group(1) if income else None,
            financing.group(1) if financing else None,
            "rejected",
            reason,
        )

    normalized = normalize_oge_asset(stripped)
    return ParsedAssetSemantic(
        normalized.name,
        normalized.canonical_key,
        normalized.category,
        amount.group(0) if amount else None,
        income.group(1) if income else None,
        financing.group(1) if financing else None,
        normalized.quality,
        normalized.rejected_reason,
    )
