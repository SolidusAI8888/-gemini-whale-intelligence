from __future__ import annotations

import re


class ReportQualityError(RuntimeError):
    pass


def _cabinet_section(html: str) -> str:
    # Match the complete section, including its internal <h2>. The prior regex
    # stopped at the section's own heading and could therefore inspect an empty
    # string in real reports while synthetic tests still passed.
    match = re.search(
        r'<section id="v40-cabinet-oge-radar">(.*?)</section>',
        html or "",
        re.I | re.S,
    )
    return match.group(1) if match else ""


def _parse_billions(label: str) -> float | None:
    match = re.fullmatch(r"\$([0-9][0-9,]*(?:\.\d+)?)B", label.strip(), re.I)
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def validate_report_html(html: str) -> None:
    """Fail closed before email delivery when known report regressions return."""
    if not html or "Gemini-美股聪明钱_政商巨鲸行动追踪" not in html:
        raise ReportQualityError("Report HTML is empty or missing the expected title")

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
            raise ReportQualityError(f"OGE semantic quality gate failed: {pattern}")

    header = re.search(r"今日新增/变化可信记录：\s*(\d+)\s*条", html)
    overview = re.search(r"本次新增可信记录\s*(\d+)\s*条", html)
    if header and overview and header.group(1) != overview.group(1):
        raise ReportQualityError(
            f"New-record count mismatch: header={header.group(1)} overview={overview.group(1)}"
        )

    # A single 13F position above $5T is not credible for this radar and is a
    # strong signature of the historical x1000 unit bug.
    for label in re.findall(r"\$[0-9][0-9,]*(?:\.\d+)?B", html):
        billions = _parse_billions(label)
        if billions is not None and billions > 5_000:
            raise ReportQualityError(f"13F/holding amount exceeds $5T sanity limit: {label}")


validate_report_html_for_tests = validate_report_html
cabinet_section_for_tests = _cabinet_section
