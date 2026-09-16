from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class NormalizedAsset:
    name: str
    canonical_key: str
    category: str
    quality: str
    rejected_reason: str | None = None


_NOISE_ONLY = re.compile(
    r"^(?:n/?a\s*)?(?:on demand|interest|rent or royalties|dividends?|capital gains?|"
    r"net distributive income|rate term|secured facility|government guaranteed collateral\)?|"
    r"borrower\)?|none(?:\s*\(or less\)?)?|\(?\s*or less\s*\)?|more than|greater than|"
    r"up to|approximately|estimated)$",
    re.I,
)

_INCOME_LABEL_PREFIX = re.compile(
    r"^(?:dividends?|crop sales|interest(?: income)?|rent or royalties|capital gains?|"
    r"net distributive income)\b",
    re.I,
)

_ENTITY_PATTERNS = (
    re.compile(r"([A-Z][A-Za-z0-9&'.,\- ]{2,100}?\b(?:L\.P\.?|LP|LLC|L\.L\.C\.?|Trust))(?=\s|$|[,;)])", re.I),
    re.compile(r"([A-Z][A-Za-z0-9&'.,\- ]{2,100}?\b(?:Inc\.?|Corp\.?|Corporation|Company|Co\.?)(?:\s*\([A-Z.\-]{1,8}\))?(?:\s*\(Class\s+[AB]\))?)(?=\s|$|[,;)])", re.I),
    re.compile(r"([A-Z][A-Za-z0-9&'.,\- ]{2,100}?\bN\.A\.?)(?=\s|$|[,;)])", re.I),
)


def _collapse(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" -:;,|")


def _strip_table_noise(text: str) -> str:
    value = _collapse(text)
    value = re.sub(r"^(?:\d+(?:\.\d+)*\s+)+", "", value)
    value = re.sub(r"^(?:N/?A\s+|No\s+|Yes\s+)+", "", value, flags=re.I)
    value = re.sub(r"^(?:RATE TERM\s+\d*\s*|ON DEMAND\s+\d*\s*)", "", value, flags=re.I)
    value = re.sub(r"\s+See Endnote\b.*$", "", value, flags=re.I)
    value = re.sub(r"\s+(?:N/?A\s+)?(?:Over\s+\$?[\d,]+|\$?[\d,]+\s*[–—-]\s*\$?[\d,]+).*$", "", value, flags=re.I)
    value = re.sub(
        r"\s+(?:secured facility|on demand|government guaranteed collateral\)?|interest|"
        r"rent or royalties|dividends?|capital gains?|net distributive income)$",
        "",
        value,
        flags=re.I,
    )
    value = re.sub(r"\b(LLC|L\.L\.C\.|L\.P\.|N\.A\.)\s*,\s*(?:co|company)\.?$", r"\1", value, flags=re.I)
    return _collapse(value)


def _trim_container_prefix(candidate: str) -> str:
    value = _collapse(candidate)
    nested = re.search(r"\bNo\s+\d+(?:\.\d+)*\s+([A-Z].+)$", value, re.I)
    if nested:
        value = _collapse(nested.group(1))
    return value


def _best_entity(text: str) -> str:
    candidates: list[str] = []
    for pattern in _ENTITY_PATTERNS:
        for match in pattern.finditer(text):
            candidates.append(_trim_container_prefix(match.group(1)))
    if not candidates:
        return ""
    last = candidates[-1]
    equivalent = [
        item for item in candidates
        if item.lower().endswith(last.lower()) or last.lower().endswith(item.lower())
    ]
    return min(equivalent or [last], key=len)


def _standardize_legal_suffixes(name: str) -> str:
    value = _collapse(name)
    value = re.sub(r"N\.A\.?(?=\s|$|[,;)])", "N.A.", value, flags=re.I)
    value = re.sub(r"L\.P\.?(?=\s|$|[,;)])", "L.P.", value, flags=re.I)
    value = re.sub(r"L\.L\.C\.?(?=\s|$|[,;)])", "L.L.C.", value, flags=re.I)
    value = re.sub(r"(?<![A-Za-z])LP(?=\s|$|[,;)])", "L.P.", value, flags=re.I)
    value = re.sub(r"(?<![A-Za-z])LLC(?=\s|$|[,;)])", "LLC", value, flags=re.I)
    return _collapse(value)


def _category(name: str) -> str:
    lower = name.lower()
    if re.search(r"bitcoin|ethereum|crypto|digital asset|token", lower):
        return "加密资产"
    if re.search(r"real estate|property|land|building|commercial|royalty interest", lower):
        return "房地产/商业权益"
    if re.search(r"(?:^|\s|[,;(])(?:l\.p\.|lp|llc|l\.l\.c\.)(?=\s|$|[,;)])|trust|limited partnership|private equity|venture", lower):
        return "私募/LLC/信托"
    if re.search(r"\b(?:etf|mutual fund|index fund|fund)\b", lower):
        return "ETF/基金"
    if re.search(r"\b(?:treasury|municipal bond|corporate bond|debenture|fixed income)\b", lower):
        return "债券"
    if re.search(r"\([A-Z.\-]{1,8}\)|\bclass\s+[ab]\b", name, re.I):
        return "股票/上市证券"
    if re.search(r"\b(?:inc\.?|corp\.?|corporation|company|co\.?)\b|n\.a\.(?=\s|$|[,;)])", name, re.I):
        return "公司权益/商业权益"
    return "其他资产"


def normalize_oge_asset(value: object) -> NormalizedAsset:
    raw = _collapse(value)
    cleaned = _strip_table_noise(raw)
    if not cleaned or _NOISE_ONLY.fullmatch(cleaned):
        return NormalizedAsset("", "", "其他资产", "rejected", "noise_or_financing_term")

    if _INCOME_LABEL_PREFIX.match(cleaned) and not _best_entity(cleaned):
        return NormalizedAsset("", "", "其他资产", "rejected", "income_label_not_asset")

    entity = _best_entity(cleaned)
    name = _standardize_legal_suffixes(_strip_table_noise(entity or cleaned))
    if not name or _NOISE_ONLY.fullmatch(name):
        return NormalizedAsset("", "", "其他资产", "rejected", "no_asset_entity")

    residue = re.sub(
        r"\b(?:n/?a|on demand|rate term|secured facility|government guaranteed collateral|"
        r"interest|rent or royalties|see endnote|no|yes)\b",
        " ",
        name,
        flags=re.I,
    )
    letters = re.sub(r"[^A-Za-z]", "", residue)
    if len(letters) < 4:
        return NormalizedAsset("", "", "其他资产", "rejected", "insufficient_entity_text")

    canonical = re.sub(r"\b(?:incorporated|corporation|company)\b", " ", name.lower())
    canonical = re.sub(r"[^a-z0-9]+", " ", canonical)
    canonical = re.sub(r"\s+", " ", canonical).strip()
    return NormalizedAsset(name, canonical, _category(name), "accepted")
