from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)


@dataclass
class SecClient:
    user_agent: str
    min_interval_seconds: float = 0.12  # SEC guidance is <=10 requests/sec; this stays below it.

    def __post_init__(self) -> None:
        self._last_request_at = 0.0
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)

    def get_json(self, url: str, timeout: int = 30) -> Any:
        self._rate_limit()
        response = self.session.get(url, timeout=timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.json()

    def get_text(self, url: str, timeout: int = 30) -> str:
        self._rate_limit()
        response = self.session.get(url, timeout=timeout)
        self._last_request_at = time.monotonic()
        response.raise_for_status()
        return response.text


    def browse_form4_atom(self, cik_or_ticker: str, count: int = 100) -> str:
        # EDGAR browse with owner=include is important for issuer-level Form 4 discovery.
        # Many Form 4 filings are stored under the reporting owner's CIK, not the issuer CIK,
        # so submissions/CIK{issuer}.json can miss them. The Atom feed provides the actual
        # filing href/base path.
        url = (
            "https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={cik_or_ticker}&type=4&owner=include&count={count}&output=atom"
        )
        return self.get_text(url)

    def discover_xml_document_url_from_base(self, base: str) -> str | None:
        base = base.rstrip("/")
        index_url = f"{base}/index.json"
        try:
            data = self.get_json(index_url)
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not read filing index %s: %s", index_url, exc)
            return None
        items = data.get("directory", {}).get("item", [])
        xml_names = [i.get("name") for i in items if str(i.get("name", "")).lower().endswith(".xml")]
        for name in xml_names:
            lowered = str(name).lower()
            if "primary_doc" in lowered or "ownership" in lowered or "form4" in lowered:
                return f"{base}/{name}"
        if xml_names:
            return f"{base}/{xml_names[0]}"
        return None

    def submissions(self, cik10: str) -> dict[str, Any]:
        return self.get_json(f"https://data.sec.gov/submissions/CIK{cik10}.json")

    @staticmethod
    def filing_base_url(cik10: str, accession_number: str) -> str:
        cik_no_zeros = str(int(cik10))
        accession_no_dashes = accession_number.replace("-", "")
        return f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}"

    def filing_document_url(self, cik10: str, accession_number: str, primary_document: str | None) -> str:
        base = self.filing_base_url(cik10, accession_number)
        if primary_document:
            return f"{base}/{primary_document}"
        return f"{base}/ownership.xml"

    def discover_xml_document_url(self, cik10: str, accession_number: str) -> str | None:
        base = self.filing_base_url(cik10, accession_number)
        index_url = f"{base}/index.json"
        try:
            data = self.get_json(index_url)
        except Exception as exc:  # noqa: BLE001
            log.debug("Could not read filing index %s: %s", index_url, exc)
            return None
        items = data.get("directory", {}).get("item", [])
        xml_names = [i.get("name") for i in items if str(i.get("name", "")).lower().endswith(".xml")]
        for name in xml_names:
            lowered = str(name).lower()
            if "primary_doc" in lowered or "ownership" in lowered or "form4" in lowered:
                return f"{base}/{name}"
        if xml_names:
            return f"{base}/{xml_names[0]}"
        return None
