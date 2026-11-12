"""ClinicalTrials.gov API v2. Paginación por token opaco (`nextPageToken`)."""

import logging
from collections.abc import Iterator

import httpx

from onco_research_ai.ingestion.http import get_json
from onco_research_ai.ingestion.landscape import CONDITION

logger = logging.getLogger(__name__)

SOURCE = "clinicaltrials"
URL = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 200  # el máximo permitido es 1000; 200 mantiene cada respuesta manejable


def query_info() -> dict:
    return {"url": URL, "query.cond": CONDITION, "pageSize": PAGE_SIZE}


def count_records(page: dict) -> int:
    return len(page["studies"])


def iter_pages(client: httpx.Client, max_pages: int | None = None) -> Iterator[dict]:
    params = {"query.cond": CONDITION, "countTotal": "true", "pageSize": PAGE_SIZE}
    token: str | None = None
    n = 0
    while True:
        page = get_json(
            client, URL, {**params, **({"pageToken": token} if token else {})}
        )
        yield page
        n += 1
        token = page.get("nextPageToken")
        if not token or (max_pages and n >= max_pages):
            break
