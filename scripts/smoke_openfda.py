import json
from pathlib import Path

import httpx

URL = "https://api.fda.gov/drug/label.json"
OUT = Path("data/smoke")


def fetch_page(params: dict, skip: int) -> dict:
    """Paginación por offset: 'skip' = cuántos resultados saltar, 'limit' = cuántos traer."""
    response = httpx.get(URL, params={**params, "skip": skip}, timeout=30)
    response.raise_for_status()
    return response.json()


def show(page: dict) -> None:
    for label in page["results"]:
        fda = label.get("openfda", {})
        print(
            f"{label['set_id'][:8]}… | v{label.get('version')} | {label.get('effective_time')} | "
            f"{fda.get('generic_name', ['?'])[0]} ({', '.join(fda.get('brand_name', ['?']))}) | "
            f"{fda.get('manufacturer_name', ['?'])[0]}"
        )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    # 1) Todas las fichas cuya indicación menciona melanoma, paginando con skip
    params = {"search": "indications_and_usage:melanoma", "limit": 5}
    page1 = fetch_page(params, skip=0)
    meta = page1["meta"]["results"]
    print("total:", meta["total"], "| skip:", meta["skip"], "| limit:", meta["limit"])
    show(page1)
    print("\n--- Página 2 (skip=5) ---")
    page2 = fetch_page(params, skip=5)
    show(page2)

    # 2) Una ficha concreta: un fármaco de referencia
    enc = fetch_page(
        {"search": 'openfda.generic_name:"encorafenib"', "limit": 1}, skip=0
    )
    (OUT / "openfda_encorafenib.json").write_text(
        json.dumps(enc, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    label = enc["results"][0]
    print("\n--- Encorafenib: secciones de la ficha ---")
    for key, value in label.items():
        if isinstance(value, list) and value and isinstance(value[0], str):
            print(f"  {key}: {len(value[0])} chars")
    print(
        "\nindications_and_usage[0][:300]:\n", label["indications_and_usage"][0][:300]
    )


if __name__ == "__main__":
    main()
