from __future__ import annotations

import pytest

from app.domain.asset_quality import normalize_oge_asset
from app.reports.quality_gate import ReportQualityError, validate_report_html_for_tests


def _base_html(cabinet_body: str = "", count: int = 2) -> str:
    return f'''<!doctype html><html><body>
<h1>Gemini-美股聪明钱_政商巨鲸行动追踪</h1>
<div class="big-change">今日新增/变化可信记录：{count} 条</div>
<section id="v40-daily-changes-overview"><p>本次新增可信记录 {count} 条：主动买入 1；机构13F持仓 1。</p></section>
<section id="v40-cabinet-oge-radar"><table><tbody>{cabinet_body}</tbody></table></section>
</body></html>'''


def test_trailing_llc_column_fragment_is_removed():
    normalized = normalize_oge_asset("DFI BD, LLC, co")
    assert normalized.quality == "accepted"
    assert normalized.name == "DFI BD, LLC"


def test_release_gate_accepts_clean_report():
    validate_report_html_for_tests(_base_html('<tr><td><b>Bank of America, N.A.</b></td></tr>'))


@pytest.mark.parametrize(
    "asset",
    [
        "Over $50,000,000",
        "Dividends $100,001",
        "Crop Sales $51,180",
        "Interest $25,000",
        "# EMPLOYER OR PARTY CITY, STATE STATUS AND TERMS DATE",
        "DFI BD, LLC, co",
    ],
)
def test_release_gate_rejects_known_oge_regressions(asset: str):
    with pytest.raises(ReportQualityError):
        validate_report_html_for_tests(_base_html(f'<tr><td><b>{asset}</b></td></tr>'))


def test_release_gate_rejects_new_count_mismatch():
    html = _base_html(count=2).replace("本次新增可信记录 2 条", "本次新增可信记录 3 条")
    with pytest.raises(ReportQualityError):
        validate_report_html_for_tests(html)


def test_release_gate_rejects_trillion_scale_13f_regression():
    html = _base_html() + '<td>$43197.45B</td>'
    with pytest.raises(ReportQualityError):
        validate_report_html_for_tests(html)
