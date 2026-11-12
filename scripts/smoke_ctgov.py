import json
from pathlib import Path

import httpx

URL = "https://clinicaltrials.gov/api/v2/studies"
OUT = Path("data/smoke")


def fetch_page(params: dict, token: str | None = None) -> dict:
    """Pide UNA página de resultados. Si hay token, pide la página que sigue a ese token."""
    if token:
        params = {**params, "pageToken": token}  # copia: no modificamos el dict original
    response = httpx.get(URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def nct_ids(page: dict) -> list[str]:
    return [s["protocolSection"]["identificationModule"]["nctId"] for s in page["studies"]]


def main() -> None:
    params = {
        "query.cond": "melanoma",
        "countTotal": "true",  # Es para que traiga el total de ensayos que cumplen con el filtro
        "pageSize": 5,  # Trae 5 ensayos por respuesta [No todos los que coinciden pq sería mucho]
    }
    OUT.mkdir(parents=True, exist_ok=True)

    # Página 1: sin token
    page1 = fetch_page(params)
    (OUT / "ctgov.json").write_text(
        json.dumps(page1, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("totalCount:", page1["totalCount"])
    token = page1.get("nextPageToken") # Como solo pedimos 5 ensayos, para pedir los de la siguiente pagina, repetimos la consulta + el nextPageToken, hasta que la respuesta ya no traiga el nextPageToken
    print("nextPageToken:", token)
    for study in page1["studies"]:
        ident = study["protocolSection"]["identificationModule"]
        print(ident["nctId"], "|", ident["briefTitle"])

    # Página 2: la misma consulta + el token de la página 1
    page2 = fetch_page(params, token)
    print("\n--- Página 2 ---")
    for study in page2["studies"]:
        ident = study["protocolSection"]["identificationModule"]
        print(ident["nctId"], "|", ident["briefTitle"])

    # Comprobación: las dos páginas no deben compartir ensayos
    repetidos = set(nct_ids(page1)) & set(nct_ids(page2))
    print("\nEnsayos repetidos entre página 1 y 2:", repetidos or "ninguno")


if __name__ == "__main__":
    main()
