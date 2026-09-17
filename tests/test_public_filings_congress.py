from datetime import date

from app.collectors.public_filings_congress import _amount_midpoint, _parts_for_cutoff


def test_public_filings_parts_cover_every_year_and_growth_part():
    parts = _parts_for_cutoff(date(2025, 1, 1), date(2026, 9, 17))
    assert parts == ["2026-1", "2026-2", "2026-3", "2025-1", "2025-2", "2025-3"]


def test_public_filings_amount_uses_statutory_range_midpoint():
    assert _amount_midpoint(1_001, 15_000) == 8_000.5
    assert _amount_midpoint(None, 15_000) is None
