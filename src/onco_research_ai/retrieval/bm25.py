"""Búsqueda por palabras exactas (BM25) sobre los MISMOS trozos que hay en Qdrant.

BM25 puntúa un trozo según cuántas veces aparecen en él las palabras de la pregunta, dando más
peso a las palabras raras ("mk-3475", "relatlimab") que a las comunes ("patients"). Es lo que
falla en la búsqueda por significado: nombres propios, códigos y siglas.

El índice se construye leyendo los trozos de Qdrant (así el corpus es idéntico) y se guarda en
data/indexes/bm25.pkl.
"""

import logging
import pickle
import re
from pathlib import Path

import numpy as np
from rank_bm25 import BM25Okapi

from onco_research_ai.storage import vectorstore

logger = logging.getLogger(__name__)
INDEX_PATH = Path("data/indexes/bm25_chunks.pkl")
TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "were",
    "with",
    "which",
    "what",
    "who",
    "how",
    "do",
    "does",
    "did",
    "than",
    "then",
    "there",
    "these",
    "those",
    "into",
    "after",
    "before",
    "between",
    "during",
    "patients",
    "patient",
    "study",
    "studies",
}


def tokenize(text: str) -> list[str]:
    """'MK-3475 (pembrolizumab)' -> ['mk-3475', 'mk', '3475', 'pembrolizumab']."""
    out = []
    for tok in TOKEN.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        out.append(tok)
        if "-" in tok:  # el código entero y sus partes: "mk-3475" y "mk", "3475"
            out.extend(p for p in tok.split("-") if p and p not in STOPWORDS)
    return out


def matches(payload: dict, filters: dict) -> bool:
    """Mismo significado que los filtros de Qdrant: igualdad, o 'contiene' si el campo es lista."""
    for key, want in filters.items():
        if want is None:
            continue
        have = payload.get(key)
        if isinstance(have, list):
            if want not in have:
                return False
        elif have != want:
            return False
    return True


class BM25Index:
    def __init__(self, ids: list[str], payloads: list[dict]):
        self.ids = ids
        self.payloads = payloads
        self.bm25 = BM25Okapi([tokenize(p["text"]) for p in payloads])

    @classmethod
    def build(cls, collection: str = "chunks_minilm") -> "BM25Index":
        client = vectorstore.get_client()
        ids, payloads, offset = [], [], None
        while True:
            points, offset = client.scroll(
                collection,
                limit=2000,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            ids += [str(p.id) for p in points]
            payloads += [p.payload for p in points]
            if offset is None:
                break
        logger.info("BM25: %d trozos leídos de %s", len(ids), collection)
        index = cls(ids, payloads)
        INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Se guardan solo los datos (no la clase): BM25 se reconstruye al cargar en ~3 s.
        INDEX_PATH.write_bytes(pickle.dumps({"ids": ids, "payloads": payloads}))
        return index

    @classmethod
    def load(cls) -> "BM25Index":
        if not INDEX_PATH.exists():
            return cls.build()
        data = pickle.loads(INDEX_PATH.read_bytes())
        return cls(data["ids"], data["payloads"])

    def search(
        self, query: str, k: int = 50, **filters
    ) -> list[tuple[str, float, dict]]:
        scores = self.bm25.get_scores(tokenize(query))
        order = np.argsort(-scores)
        out = []
        for i in order:
            if scores[i] <= 0:
                break
            if matches(self.payloads[i], filters):
                out.append((self.ids[i], float(scores[i]), self.payloads[i]))
                if len(out) == k:
                    break
        return out


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    BM25Index.build()
    logger.info("Índice guardado en %s", INDEX_PATH)
