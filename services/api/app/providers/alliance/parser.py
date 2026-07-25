"""Parse Alliance Parts Connection search HTML into normalised raw records.

The Parts Connection search (`/en/Search/StartsWith`) returns an HTML results
table: one row per matching model, each linking to that model's assembly
drawings. This maps each row to the raw-record shape the connector
normalises. Tolerant: returns [] when the results table is absent or empty.

Pinned against a captured, sanitised SC60 response (2026-07-25).
"""

import logging
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_PARTS_BASE = "https://pc.alliancels.net"
_MANUFACTURER = "Alliance Laundry Systems"


def parse_search_html(body: bytes) -> list[dict]:
    soup = BeautifulSoup(body, "html.parser")
    table = soup.find("table", class_="list")
    if table is None:
        logger.warning("alliance parts search: no results table found")
        return []
    tbody = table.find("tbody") or table

    records: list[dict] = []
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 5:
            continue
        link = cells[0].find("a")
        if link is None:
            continue
        model = link.get_text(strip=True)
        if not model:
            continue

        href = link.get("href", "")
        params = parse_qs(urlparse(href).query)
        model_id = (params.get("ModelId") or [""])[0]
        manual_id = (params.get("ManualId") or [""])[0]

        product_type = cells[1].get_text(strip=True)
        product_family = cells[2].get_text(strip=True)
        manual_comments = cells[4].get_text(strip=True)

        source_reference = f"als-model-{model_id}" if model_id else f"als-model-{model}"
        source_url = f"{_PARTS_BASE}{href}" if href.startswith("/") else href
        metadata = {
            key: value
            for key, value in {
                "product_type": product_type,
                "product_family": product_family,
                "manual_id": manual_id,
                "model_id": model_id,
            }.items()
            if value
        }
        records.append(
            {
                "source_reference": source_reference,
                "result_type": "model",
                "title": model,
                "model": model,
                "description": manual_comments or None,
                "manufacturer": _MANUFACTURER,
                "document_type": "assembly_drawings",
                "source_url": source_url,
                "metadata": metadata,
            }
        )
    return records
