"""Guardado de datos crudos: una carpeta por descarga, inmutable, con manifiesto."""

import json
import logging
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def save_run(
    source: str,
    query: dict,
    pages: Iterable[dict],
    count_records: Callable[[dict], int],
    is_error: Callable[[dict], bool] = lambda page: False,
    root: Path = Path("data/raw"),
) -> Path:
    """Guarda cada página tal cual la devolvió la API y, al final, un manifest.json.

    data/raw/<fuente>/<fecha-hora>/page_0001.json ... manifest.json

    Dos niveles de "no usable":
    - SIN manifest.json: la descarga se cortó a medias (el proceso murió).
    - CON manifest.json pero status="partial": terminó, pero hubo páginas con error.
    Solo status="complete" es una descarga fiable (ver `latest_complete_run`).
    """
    started = datetime.now(UTC)
    run_dir = root / source / started.strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(
        parents=True, exist_ok=False
    )  # nunca sobrescribir una descarga previa

    n_pages = 0
    n_records = 0
    n_errors = 0
    for n_pages, page in enumerate(pages, start=1):
        (run_dir / f"page_{n_pages:04d}.json").write_text(
            json.dumps(page, ensure_ascii=False), encoding="utf-8"
        )
        n_records += count_records(page)
        n_errors += is_error(page)
        logger.info(
            "%s: página %d guardada (%d registros acumulados)",
            source,
            n_pages,
            n_records,
        )

    manifest = {
        "source": source,
        "query": query,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
        "n_pages": n_pages,
        "n_records": n_records,
        "n_errors": n_errors,
        "status": "complete" if n_errors == 0 and n_pages > 0 else "partial",
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if manifest["status"] == "complete":
        logger.info("%s: descarga completa -> %s", source, run_dir)
    else:
        logger.error(
            "%s: descarga PARCIAL (%d páginas con error de %d) -> %s",
            source,
            n_errors,
            n_pages,
            run_dir,
        )
    return run_dir


def read_manifest(run_dir: Path) -> dict:
    return json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))


def latest_complete_run(source: str, root: Path = Path("data/raw")) -> Path | None:
    """La descarga más reciente que sea fiable; None si no hay ninguna.

    Ignora carpetas sin manifest.json (cortadas) y las de status="partial".
    Los nombres de carpeta son fechas ISO, así que el orden alfabético es cronológico.
    """
    for run_dir in sorted((root / source).glob("*"), reverse=True):
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists() and read_manifest(run_dir)["status"] == "complete":
            return run_dir
    return None
