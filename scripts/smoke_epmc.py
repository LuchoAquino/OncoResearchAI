import json
from pathlib import Path

import httpx

URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
OUT = Path("data/smoke")


def fetch_page(params: dict, cursor: str) -> dict:
    """Pide UNA página. El cursor "*" significa 'desde el principio'."""
    response = httpx.get(URL, params={**params, "cursorMark": cursor}, timeout=30)
    response.raise_for_status()
    return response.json()


def show(page: dict) -> None:
    for art in page["resultList"]["result"]:
        abstract = art.get("abstractText", "")
        print(
            f"{art.get('source')}:{art.get('id')} | {art.get('pubYear')} | "
            f"abstract={len(abstract)} chars | {art.get('title', '')[:80]}"
        )


def main() -> None:
    params = {
        # sintaxis de Europe PMC: AND/OR, paréntesis y filtros con CAMPO:valor
        "query": "melanoma AND (encorafenib OR binimetinib) AND HAS_ABSTRACT:y",
        "format": "json",
        "resultType": "core",  # "lite" (por defecto) NO trae el abstract; "core" sí
        "pageSize": 5,
    }
    OUT.mkdir(parents=True, exist_ok=True)

    # Página 1: cursor inicial "*"
    page1 = fetch_page(params, "*")
    (OUT / "epmc.json").write_text(
        json.dumps(page1, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("hitCount:", page1["hitCount"])
    cursor = page1.get("nextCursorMark")
    print("nextCursorMark:", cursor)
    show(page1)

    # Página 2: la misma consulta + el cursor que devolvió la página 1
    page2 = fetch_page(params, cursor)
    print("\n--- Página 2 ---")
    show(page2)

    ids1 = {a["id"] for a in page1["resultList"]["result"]}
    ids2 = {a["id"] for a in page2["resultList"]["result"]}
    print("\nRepetidos entre página 1 y 2:", (ids1 & ids2) or "ninguno")

    # Qué campos tiene un artículo (para decidir luego qué guardar)
    print("\nCampos de un artículo:", sorted(page1["resultList"]["result"][0].keys()))


if __name__ == "__main__":
    main()
