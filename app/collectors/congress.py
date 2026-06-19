from __future__ import annotations

"""
Congress collector placeholder.

The official House and Senate disclosures are the correct authority, but they are not
as stable as SEC's JSON/XML endpoints for unattended parsing. This module defines the
same normalized trade schema used by SEC Form 4 so a later connector can plug in:
- House Financial Disclosure PDFs / XML / exports
- Senate eFD periodic transaction reports
- Paid structured APIs such as Quiver Quantitative or Capitol Trades, if licensed

For MVP, this returns an empty list instead of scraping brittle pages.
"""


def collect_congress_trades(*_args, **_kwargs) -> list[dict]:
    return []
