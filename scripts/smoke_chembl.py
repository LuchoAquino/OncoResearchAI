import json
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

BASE = "https://www.ebi.ac.uk/chembl/api/data"
OUT = Path("data/smoke")
DRUGS = ["pembrolizumab", "nivolumab", "ipilimumab", "encorafenib", "binimetinib"]


def is_retryable(exc: BaseException) -> bool:
    """Reintentar solo fallos TRANSITORIOS: 5xx, 429 (demasiadas peticiones) y errores de red.
    Un 404 o 400 es culpa nuestra: reintentar no lo arreglaría."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=20),  # espera 1s, 2s, 4s, 8s...
    reraise=True,  # si se agotan los intentos, lanza el error original
)
def get(path: str, **params) -> dict:
    response = httpx.get(f"{BASE}/{path}.json", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def find_molecule(name: str) -> dict:
    """La búsqueda devuelve varios candidatos; nos quedamos con el de nombre exacto."""
    hits = get("molecule/search", q=name, limit=10)["molecules"]
    exact = [m for m in hits if (m.get("pref_name") or "").lower() == name.lower()]
    return (exact or hits)[0]


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    profiles = {}
    for name in DRUGS:
        mol = find_molecule(name)
        chembl_id = mol["molecule_chembl_id"]
        synonyms = sorted({s["molecule_synonym"] for s in mol["molecule_synonyms"]})
        mechs = get("mechanism", molecule_chembl_id=chembl_id)["mechanisms"]
        profiles[name] = {"molecule": mol, "mechanisms": mechs}
        print(f"\n{mol['pref_name']} | {chembl_id} | max_phase={mol.get('max_phase')}")
        print("  sinónimos:", ", ".join(synonyms[:8]))
        for m in mechs:
            print(f"  mecanismo: {m['mechanism_of_action']} ({m['action_type']})")

    (OUT / "chembl_profiles.json").write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # Paginación de ChEMBL: viene en 'page_meta' (limit, offset, total_count, next)
    page = get("mechanism", limit=5)
    print("\npage_meta:", page["page_meta"])


if __name__ == "__main__":
    main()
