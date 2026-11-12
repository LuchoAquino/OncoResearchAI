"""openFDA drug/label. Paginación por offset (`skip` + `limit`)."""

import logging
from collections.abc import Iterator

import httpx

from onco_research_ai.ingestion.http import get_json
from onco_research_ai.ingestion.landscape import CONDITION

logger = logging.getLogger(__name__)

SOURCE = "openfda"
URL = "https://api.fda.gov/drug/label.json"
PAGE_SIZE = 100


def query_info() -> dict:
    return {
        "url": URL,
        "search": f"indications_and_usage:{CONDITION}",
        "limit": PAGE_SIZE,
    }


def count_records(page: dict) -> int:
    return len(page["results"])


def iter_pages(client: httpx.Client, max_pages: int | None = None) -> Iterator[dict]:
    params = {"search": f"indications_and_usage:{CONDITION}", "limit": PAGE_SIZE}
    skip = 0
    n = 0
    while True:
        page = get_json(client, URL, {**params, "skip": skip})
        yield page
        n += 1
        skip += PAGE_SIZE
        # con offset sabemos cuándo parar: cuando saltamos más de lo que existe
        if skip >= page["meta"]["results"]["total"] or (max_pages and n >= max_pages):
            break
