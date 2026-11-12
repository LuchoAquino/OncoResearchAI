"""Lee Postgres, trocea, calcula embeddings y los guarda en Qdrant.

uv run python -m onco_research_ai.retrieval.index --model minilm
"""

import argparse
import logging
import time
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from onco_research_ai.processing.chunking import Chunk, split_text
from onco_research_ai.retrieval.embedder import Embedder
from onco_research_ai.storage import vectorstore
from onco_research_ai.storage.db import get_engine
from onco_research_ai.storage.models import (
    Drug,
    Label,
    LabelDrug,
    LabelSection,
    Publication,
    PublicationDrug,
    Trial,
    TrialDrug,
)

logger = logging.getLogger(__name__)
CHUNK_TOKENS = (
    180  # deja margen bajo el límite de 256 de MiniLM para el título que se antepone
)


def _drug_names(s: Session, link, key_col) -> dict[str, list[str]]:
    out = defaultdict(list)
    for key, name in s.execute(
        select(key_col, Drug.canonical_name).join(Drug, Drug.id == link.drug_id)
    ):
        out[key].append(name)
    return out


def build_chunks(s: Session, count) -> list[Chunk]:
    chunks: list[Chunk] = []
    trial_drugs = _drug_names(s, TrialDrug, TrialDrug.nct_id)
    pub_drugs = _drug_names(s, PublicationDrug, PublicationDrug.publication_id)
    label_drugs = _drug_names(s, LabelDrug, LabelDrug.set_id)

    # 1) Ensayos: título + resumen (casi siempre cabe en un solo trozo)
    for t in s.scalars(select(Trial)):
        body = f"{t.brief_title}. {t.brief_summary or ''}".strip()
        for i, text in enumerate(split_text(body, count, CHUNK_TOKENS)):
            chunks.append(
                Chunk(
                    t.nct_id,
                    i,
                    text,
                    {
                        "source": "trial",
                        "doc_id": t.nct_id,
                        "title": t.brief_title,
                        "text": text,
                        "drugs": trial_drugs.get(t.nct_id, []),
                        "phases": t.phases,
                        "sponsor_class": t.sponsor_class,
                        "status": t.overall_status,
                        "year": t.start_date.year if t.start_date else None,
                        "url": f"https://clinicaltrials.gov/study/{t.nct_id}",
                    },
                )
            )

    # 2) Artículos: el título se antepone a CADA trozo para que no pierda contexto
    for p in s.scalars(select(Publication).where(Publication.abstract.is_not(None))):
        for i, body in enumerate(split_text(p.abstract, count, CHUNK_TOKENS)):
            text = f"{p.title} {body}"
            chunks.append(
                Chunk(
                    p.id,
                    i,
                    text,
                    {
                        "source": "publication",
                        "doc_id": p.id,
                        "title": p.title,
                        "text": text,
                        "drugs": pub_drugs.get(p.id, []),
                        "year": p.pub_year,
                        "journal": p.journal,
                        "url": f"https://europepmc.org/article/{p.source}/{p.id.split(':')[1]}",
                    },
                )
            )

    # 3) Fichas FDA: una sección puede tener 59 000 tokens, de ahí el troceado
    rows = s.execute(
        select(LabelSection, Label).join(Label, Label.set_id == LabelSection.set_id)
    )
    for sec, lab in rows:
        name = lab.brand_name or lab.generic_name or "FDA label"
        for i, body in enumerate(split_text(sec.text, count, CHUNK_TOKENS)):
            text = f"{name} — {sec.name}: {body}"
            chunks.append(
                Chunk(
                    f"{lab.set_id}/{sec.name}",
                    i,
                    text,
                    {
                        "source": "label",
                        "doc_id": lab.set_id,
                        "title": name,
                        "text": text,
                        "section": sec.name,
                        "drugs": label_drugs.get(lab.set_id, []),
                        "year": lab.effective_date.year if lab.effective_date else None,
                        "url": f"https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid={lab.set_id}",
                    },
                )
            )
    return chunks


def main(model_key: str, batch: int) -> None:
    emb = Embedder(model_key)
    with Session(get_engine()) as s:
        chunks = build_chunks(s, emb.count_tokens)
    by_source = defaultdict(int)
    for c in chunks:
        by_source[c.payload["source"]] += 1
    logger.info("%d trozos: %s", len(chunks), dict(by_source))

    client = vectorstore.get_client()
    name = vectorstore.collection_name(model_key)
    vectorstore.recreate_collection(client, name, emb.dim)

    t0 = time.time()
    for start in range(0, len(chunks), batch):
        part = chunks[start : start + batch]
        vectors = emb.encode([c.text for c in part], batch_size=32)
        vectorstore.upsert(
            client, name, [c.point_id for c in part], vectors, [c.payload for c in part]
        )
        if (start // batch) % 10 == 0:
            logger.info(
                "%d/%d trozos (%.0f s)",
                start + len(part),
                len(chunks),
                time.time() - t0,
            )
    logger.info(
        "Colección %s: %d puntos en %.0f s",
        name,
        client.count(name).count,
        time.time() - t0,
    )


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="minilm", choices=["minilm", "bge-m3"])
    ap.add_argument("--batch", type=int, default=256)
    args = ap.parse_args()
    setup_logging()
    main(args.model, args.batch)
