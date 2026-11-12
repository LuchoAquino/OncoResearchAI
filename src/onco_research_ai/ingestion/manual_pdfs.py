"""PDFs de congresos (ASCO, ESMO, SMR...) recopilados a mano -> trozos indexados con su página.

Uso:
    1. Copiar los PDF en data/manual_pdfs/
    2. (Opcional) data/manual_pdfs/metadata.csv con columnas: file,title,congress,year,url
    3. uv run python -m onco_research_ai.ingestion.manual_pdfs

Un PDF es un formato de MAQUETACIÓN, no de texto: guarda letras en posiciones de la página.
pymupdf4llm reconstruye el orden de lectura y las tablas como Markdown, página a página; así
cada trozo recuerda su página y la cita puede decir «ESMO 2025, p. 3».
Se puede repetir: borra los trozos de congresos anteriores y los vuelve a crear.
"""

import csv
import logging
import re
from pathlib import Path

import pymupdf4llm
from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue
from sqlalchemy.orm import Session

from onco_research_ai.processing.chunking import Chunk, split_text
from onco_research_ai.retrieval.bm25 import BM25Index
from onco_research_ai.retrieval.embedder import Embedder, chunk_token_counter
from onco_research_ai.storage import vectorstore
from onco_research_ai.storage.db import get_engine
from onco_research_ai.storage.load import _drug_patterns

logger = logging.getLogger(__name__)
PDF_DIR = Path("data/manual_pdfs")


def read_metadata(folder: Path) -> dict[str, dict]:
    meta_file = folder / "metadata.csv"
    if not meta_file.exists():
        return {}
    with meta_file.open(encoding="utf-8") as f:
        return {row["file"]: row for row in csv.DictReader(f)}


def pdf_pages(path: Path) -> list[tuple[int, str]]:
    """[(nº de página, texto en Markdown)], sin páginas vacías."""
    pages = pymupdf4llm.to_markdown(str(path), page_chunks=True, show_progress=False)
    return [
        (p["metadata"]["page_number"], p["text"].strip())
        for p in pages
        if p["text"].strip()
    ]


def build_chunks(folder: Path, count, patterns) -> list[Chunk]:
    meta = read_metadata(folder)
    chunks = []
    for path in sorted(folder.glob("*.pdf")):
        m = meta.get(path.name, {})
        title = m.get("title") or path.stem.replace("_", " ")
        label = " ".join(x for x in (m.get("congress"), m.get("year")) if x)
        doc_id = f"congress:{path.stem}"
        i = 0
        for page, text in pdf_pages(path):
            for body in split_text(re.sub(r"\s+", " ", text), count, 180):
                full = f"{title}{f' ({label})' if label else ''}, p. {page}: {body}"
                drugs = sorted({d for pat, _, d in patterns if pat.search(body)})
                chunks.append(
                    Chunk(
                        doc_id,
                        i,
                        full,
                        {
                            "source": "congress",
                            "doc_id": doc_id,
                            "title": title,
                            "text": full,
                            "page": page,
                            "year": int(m["year"])
                            if m.get("year", "").isdigit()
                            else None,
                            "congress": m.get("congress"),
                            "drugs": drugs,
                            "url": m.get("url") or path.resolve().as_uri(),
                        },
                    )
                )
                i += 1
        logger.info("%s: %d trozos", path.name, i)
    return chunks


def main(models: list[str]) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    with Session(get_engine()) as s:
        patterns = [(p, sy, name) for p, sy, name in _named_patterns(s)]
    chunks = build_chunks(PDF_DIR, chunk_token_counter(), patterns)
    client = vectorstore.get_client()
    only_congress = Filter(
        must=[FieldCondition(key="source", match=MatchValue(value="congress"))]
    )
    for model in models:
        name = vectorstore.collection_name(model)
        if not client.collection_exists(name):
            logger.warning(
                "Colección %s no existe: indexa primero los datos (retrieval.index)",
                name,
            )
            continue
        client.delete(name, points_selector=FilterSelector(filter=only_congress))
        if chunks:
            emb = Embedder(model)
            vectors = emb.encode([c.text for c in chunks], batch_size=32)
            vectorstore.upsert(
                client,
                name,
                [c.point_id for c in chunks],
                vectors,
                [c.payload for c in chunks],
            )
        logger.info("%s: %d trozos de congresos indexados", name, len(chunks))
    BM25Index.build()  # el índice de palabras se reconstruye para incluir (o quitar) los PDFs
    if not chunks:
        logger.info("No hay PDFs en %s: nada que indexar.", PDF_DIR)


def _named_patterns(s: Session):
    """Patrones de sinónimos con el nombre canónico del fármaco (para el payload `drugs`)."""
    from sqlalchemy import select

    from onco_research_ai.storage.models import Drug

    names = dict(s.execute(select(Drug.id, Drug.canonical_name)).all())
    return [(pat, sy, names[drug_id]) for pat, sy, drug_id in _drug_patterns(s)]


if __name__ == "__main__":
    import argparse

    from onco_research_ai.logging_config import setup_logging

    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["minilm", "medcpt"])
    setup_logging()
    main(ap.parse_args().models)
