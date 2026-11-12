"""Búsqueda híbrida: significado (vectores) + palabras exactas (BM25) + reordenación (reranker).

    pregunta ─┬─► Qdrant (denso)  top 50 ─┐
              └─► BM25            top 50 ─┴─► RRF (fusión) ─► reranker ─► top k

- RRF (Reciprocal Rank Fusion): cada lista aporta 1/(60 + posición). No compara puntuaciones
  de escalas distintas (coseno vs BM25), solo posiciones: simple y robusto.
- Reranker (cross-encoder): lee pregunta y trozo JUNTOS y puntúa su relación. Es mucho más
  preciso que comparar dos vectores calculados por separado (bi-encoder), pero lento: por eso
  solo se aplica a los ~50 candidatos, no a los 25 000 trozos.
"""

import logging
from dataclasses import dataclass, field

import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from onco_research_ai.retrieval.bm25 import BM25Index
from onco_research_ai.retrieval.embedder import DEVICE, Embedder
from onco_research_ai.storage import vectorstore

logger = logging.getLogger(__name__)
RRF_K = 60
RERANKER = "ncbi/MedCPT-Cross-Encoder"


@dataclass
class Hit:
    point_id: str
    payload: dict
    score: float
    ranks: dict = field(default_factory=dict)  # posición en cada lista (diagnóstico)

    @property
    def doc_id(self) -> str:
        return self.payload["doc_id"]


class Reranker:
    def __init__(self, name: str = RERANKER):
        self.tok = AutoTokenizer.from_pretrained(name)
        model = (
            AutoModelForSequenceClassification.from_pretrained(name).eval().to(DEVICE)
        )
        self.model = model.half() if DEVICE == "cuda" else model

    def scores(self, query: str, texts: list[str], batch_size: int = 16) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), batch_size):
            batch = self.tok(
                [[query, t] for t in texts[i : i + batch_size]],
                truncation=True,
                padding=True,
                max_length=320,  # los trozos tienen ≤180 tokens + título
                return_tensors="pt",
            ).to(DEVICE)
            with torch.inference_mode():
                out += self.model(**batch).logits.squeeze(-1).float().cpu().tolist()
        return out


class Retriever:
    """mode: "dense" | "bm25" | "hybrid". rerank solo se aplica sobre los candidatos."""

    def __init__(
        self,
        model_key: str = "minilm",  # ganador de la evaluación (eval/reports/retrieval_*.md)
        mode: str = "hybrid",
        rerank: bool = True,
        candidates: int = 50,
        rerank_top: int = 20,
        embedder: Embedder | None = None,
        bm25: BM25Index | None = None,
        reranker: Reranker | None = None,
    ):
        self.model_key, self.mode, self.candidates = model_key, mode, candidates
        self.rerank_top = rerank_top
        self.client = vectorstore.get_client()
        self.collection = vectorstore.collection_name(model_key)
        needs_dense = mode in ("dense", "hybrid")
        self.embedder = embedder or (
            Embedder(model_key, queries_only=True) if needs_dense else None
        )
        self.bm25 = bm25 or (BM25Index.load() if mode in ("bm25", "hybrid") else None)
        self.reranker = (reranker or Reranker()) if rerank else None

    def _dense(self, query: str, k: int, filters: dict) -> list[Hit]:
        vec = self.embedder.encode_queries([query])[0]
        points = vectorstore.search(self.client, self.collection, vec, k=k, **filters)
        return [Hit(str(p.id), p.payload, p.score) for p in points]

    def _bm25(self, query: str, k: int, filters: dict) -> list[Hit]:
        return [Hit(i, p, s) for i, s, p in self.bm25.search(query, k=k, **filters)]

    def search(self, query: str, k: int = 10, **filters) -> list[Hit]:
        """Trozos más relevantes (como mucho uno por documento)."""
        filters = {key: v for key, v in filters.items() if v is not None}
        lists = {}
        if self.mode in ("dense", "hybrid"):
            lists["dense"] = self._dense(query, self.candidates, filters)
        if self.mode in ("bm25", "hybrid"):
            lists["bm25"] = self._bm25(query, self.candidates, filters)

        fused: dict[str, Hit] = {}
        for name, hits in lists.items():
            for rank, h in enumerate(hits, 1):
                hit = fused.setdefault(h.point_id, Hit(h.point_id, h.payload, 0.0))
                hit.score += 1 / (RRF_K + rank) if len(lists) > 1 else h.score
                hit.ranks[name] = rank
        hits = sorted(fused.values(), key=lambda h: h.score, reverse=True)

        if self.reranker and hits:
            # Antes de reordenar, un trozo por documento: así los 20 reordenados son 20 documentos.
            hits = best_per_doc(hits)
            top, rest = hits[: self.rerank_top], hits[self.rerank_top :]
            scores = self.reranker.scores(query, [h.payload["text"] for h in top])
            for h, s in zip(top, scores, strict=True):
                h.ranks["fused"] = h.score
                h.score = s
            top.sort(key=lambda h: h.score, reverse=True)
            hits = top + rest  # los no reordenados quedan detrás, en orden de fusión
        return best_per_doc(hits)[:k]


def best_per_doc(hits: list[Hit]) -> list[Hit]:
    """Varios trozos del mismo documento ocupan sitio sin aportar: se deja el mejor de cada uno."""
    seen, out = set(), []
    for h in hits:
        if h.doc_id not in seen:
            seen.add(h.doc_id)
            out.append(h)
    return out
