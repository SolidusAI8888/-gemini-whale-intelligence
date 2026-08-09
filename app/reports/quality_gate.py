from __future__ import annotations

import os
import re


class ReportQualityError(RuntimeError):
    pass


def _cabinet_section(html: str) -> str:
    match = re.search(
        r'<section id="v40-cabinet-oge-radar">(.*?)</section>',
        html or "",
        re.I | re.S,
    )
    return match.group(1) if match else ""


def _build_sha() -> str:
    return str(os.getenv("REPORT_BUILD_SHA") or os.getenv("GITHUB_SHA") or "local")[:12]


def _parse_billions(label: str) -> float | None:
    match = re.fullmatch(r"\$([0-9][0-9,]*(?:\.\d+)?)B", label.strip(), re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def validate_report_html(html: str) -> None:
    """Fail closed before email delivery when known report regressions return."""
    build = _build_sha()
    if not html or "Gemini-美股聪明钱_政商巨鲸行动追踪" not in html:
        raise ReportQualityError(f"Report HTML is empty or missing the expected title (build={build})")

    cabinet = _cabinet_section(html)
    forbidden_oge_assets = [
        r"<b>\s*Over\s+\$",
        r"<b>\s*Dividends?\b",
        r"<b>\s*Crop Sales\b",
        r"<b>\s*Interest(?: Income)?\b",
        r"<b>\s*RATE TERM\b",
        r"<b>\s*On Demand\b",
        r"<b>\s*#?\s*EMPLOYER OR PARTY\b",
        r"<b>[^<]*\bLLC\s*,\s*co\b",
    ]
    for pattern in forbidden_oge_assets:
        if re.search(pattern, cabinet, re.I):
            raise ReportQualityError(f"OGE semantic quality gate failed (build={build}): {pattern}")

    header = re.search(r"今日新增/变化可信记录：\s*(\d+)\s*条", html)
    overview = re.search(r"本次新增可信记录\s*(\d+)\s*条", html)
    if header and overview and header.group(1) != overview.group(1):
        raise ReportQualityError(
            f"New-record count mismatch (build={build}): header={header.group(1)} overview={overview.group(1)}"
        )

    for label in re.findall(r"\$[0-9][0-9,]*(?:\.\d+)?B", html):
        billions = _parse_billions(label)
        if billions is not None and billions > 5_000:
            raise ReportQualityError(f"13F/holding amount exceeds $5T sanity limit (build={build}): {label}")


validate_report_html_for_tests = validate_report_html
cabinet_section_for_tests = _cabinet_section
