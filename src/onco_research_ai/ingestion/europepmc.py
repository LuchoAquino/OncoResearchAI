"""Europe PMC REST. Paginación por cursor (`cursorMark` / `nextCursorMark`)."""

import logging
from collections.abc import Iterator

import httpx

from onco_research_ai.ingestion.http import get_json
from onco_research_ai.ingestion.landscape import CONDITION, DRUGS, FIRST_YEAR, last_year

logger = logging.getLogger(__name__)

SOURCE = "europepmc"
URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
PAGE_SIZE = 500


def build_query() -> str:
    """melanoma y algún fármaco en TÍTULO o ABSTRACT (no en cualquier parte del texto).

    Con búsqueda en texto completo la consulta devolvía ~70 000 artículos, casi todo ruido.
    """
    drugs = " OR ".join(DRUGS)
    return (
        f"TITLE_ABS:{CONDITION} AND TITLE_ABS:({drugs}) AND HAS_ABSTRACT:y "
        f"AND PUB_YEAR:[{FIRST_YEAR} TO {last_year()}]"
    )


def query_info() -> dict:
    return {
        "url": URL,
        "query": build_query(),
        "resultType": "core",
        "pageSize": PAGE_SIZE,
    }


def count_records(page: dict) -> int:
    return len(page["resultList"]["result"])


def iter_pages(client: httpx.Client, max_pages: int | None = None) -> Iterator[dict]:
    params = {
        "query": build_query(),
        "format": "json",
        "resultType": "core",  # "lite" no incluye el abstract
        "pageSize": PAGE_SIZE,
    }
    cursor = "*"  # "*" = empezar desde el principio
    n = 0
    while True:
        page = get_json(client, URL, {**params, "cursorMark": cursor})
        if not page["resultList"]["result"]:
            break
        yield page
        n += 1
        next_cursor = page.get("nextCursorMark")
        # en la última página la API devuelve el mismo cursor que le enviamos
        if not next_cursor or next_cursor == cursor or (max_pages and n >= max_pages):
            break
        cursor = next_cursor
