"""Uso:  uv run python -m onco_research_ai.ingestion <fuente|all> [--max-pages N]"""

import argparse
import logging
from pathlib import Path

from onco_research_ai.ingestion import chembl, clinicaltrials, europepmc, openfda
from onco_research_ai.ingestion.http import make_client
from onco_research_ai.ingestion.raw_store import read_manifest, save_run
from onco_research_ai.logging_config import setup_logging

logger = logging.getLogger(__name__)

CONNECTORS = {
    "ctgov": clinicaltrials,
    "epmc": europepmc,
    "openfda": openfda,
    "chembl": chembl,
}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Descarga datos crudos de las fuentes."
    )
    parser.add_argument("source", choices=[*CONNECTORS, "all"])
    parser.add_argument(
        "--max-pages", type=int, default=None, help="límite (para pruebas)"
    )
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args(argv)

    setup_logging()
    names = list(CONNECTORS) if args.source == "all" else [args.source]
    partial: list[str] = []
    with make_client() as client:
        for name in names:
            connector = CONNECTORS[name]
            logger.info("Iniciando descarga: %s", connector.SOURCE)
            run_dir = save_run(
                source=connector.SOURCE,
                query=connector.query_info(),
                pages=connector.iter_pages(client, max_pages=args.max_pages),
                count_records=connector.count_records,
                is_error=getattr(connector, "is_error", lambda page: False),
                root=args.out,
            )
            if read_manifest(run_dir)["status"] != "complete":
                partial.append(connector.SOURCE)

    if partial:
        # código de salida != 0: un script o CI sabrá que algo no salió bien
        raise SystemExit(f"Descargas parciales: {', '.join(partial)}")


if __name__ == "__main__":
    main()
