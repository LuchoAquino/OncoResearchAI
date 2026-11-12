"""ChEMBL: no es una búsqueda paginada sino una consulta por fármaco.

Por cada fármaco de `landscape.DRUGS` guardamos su molécula (con sinónimos) y su
mecanismo de acción. Es el diccionario que usaremos para alinear las otras fuentes.
"""

import logging
from collections.abc import Iterator

import httpx

from onco_research_ai.ingestion.http import get_json
from onco_research_ai.ingestion.landscape import DRUGS

logger = logging.getLogger(__name__)

SOURCE = "chembl"
BASE = "https://www.ebi.ac.uk/chembl/api/data"


def query_info() -> dict:
    return {"base": BASE, "drugs": DRUGS}


def count_records(page: dict) -> int:
    # cada "página" es un fármaco; si falló, no cuenta como registro
    return 0 if "error" in page else 1


def is_error(page: dict) -> bool:
    return "error" in page


def find_molecule(client: httpx.Client, name: str) -> dict:
    """La búsqueda devuelve varios candidatos; preferimos el de nombre exacto."""
    hits = get_json(client, f"{BASE}/molecule/search.json", {"q": name, "limit": 10})[
        "molecules"
    ]
    exact = [m for m in hits if (m.get("pref_name") or "").lower() == name.lower()]
    candidates = exact or hits
    if not candidates:
        raise LookupError(f"ChEMBL no devolvió ninguna molécula para {name!r}")
    return candidates[0]


def iter_pages(client: httpx.Client, max_pages: int | None = None) -> Iterator[dict]:
    for i, name in enumerate(DRUGS):
        if max_pages and i >= max_pages:
            break
        try:
            molecule = find_molecule(client, name)
            mechanisms = get_json(
                client,
                f"{BASE}/mechanism.json",
                {"molecule_chembl_id": molecule["molecule_chembl_id"]},
            )["mechanisms"]
        except (httpx.HTTPError, LookupError) as exc:
            # Un fármaco fallido (tras agotar los reintentos) no debe tirar abajo la
            # descarga de los demás: lo registramos y seguimos. Queda una página con
            # "error" para poder reintentar luego solo los que faltan.
            logger.error("ChEMBL: no se pudo obtener %r: %s", name, exc)
            yield {"drug_query": name, "error": repr(exc)}
            continue
        yield {"drug_query": name, "molecule": molecule, "mechanisms": mechanisms}
