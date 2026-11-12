"""Compara configuraciones de búsqueda con el conjunto de evaluación.

Métricas (a nivel de DOCUMENTO, no de trozo):
- Recall@k: % de preguntas cuyo documento correcto aparece entre los k primeros.
- MRR@10:   media de 1/posición del documento correcto (1 si sale 1.º, 0,5 si sale 2.º...;
            0 si no está en los 10 primeros). Premia que salga ARRIBA, no solo que salga.
"""

import logging
import time
from collections import defaultdict
from datetime import date
from pathlib import Path

from onco_research_ai.evaluation.golden_set import load
from onco_research_ai.retrieval.bm25 import BM25Index
from onco_research_ai.retrieval.embedder import Embedder
from onco_research_ai.retrieval.hybrid import Reranker, Retriever

logger = logging.getLogger(__name__)
K = 10


def evaluate(retriever: Retriever, questions: list[dict]) -> dict:
    per_kind: dict[str, list[int | None]] = defaultdict(list)
    t0 = time.time()
    for q in questions:
        docs = [h.doc_id for h in retriever.search(q["question"], k=K)]
        rank = next((i for i, d in enumerate(docs, 1) if d in q["relevant"]), None)
        per_kind[q["kind"]].append(rank)
        per_kind["all"].append(rank)
    secs = (time.time() - t0) / len(questions)

    def metrics(ranks):
        n = len(ranks)
        return {
            "R@1": sum(r is not None and r <= 1 for r in ranks) / n,
            "R@5": sum(r is not None and r <= 5 for r in ranks) / n,
            "R@10": sum(r is not None for r in ranks) / n,
            "MRR": sum(1 / r for r in ranks if r) / n,
        }

    return {"by_kind": {k: metrics(v) for k, v in per_kind.items()}, "secs": secs}


def main() -> None:
    questions = load()
    bm25 = BM25Index.load()
    emb = {
        "minilm": Embedder("minilm"),
        "medcpt": Embedder("medcpt", queries_only=True),
    }
    reranker = Reranker()

    def r(model, mode, rerank=False):
        return Retriever(
            model,
            mode,
            rerank,
            embedder=emb[model],
            bm25=bm25,
            reranker=reranker if rerank else None,
        )

    configs = {
        "BM25 (palabras)": r("minilm", "bm25"),
        "Denso MiniLM": r("minilm", "dense"),
        "Denso MedCPT": r("medcpt", "dense"),
        "Híbrido MiniLM": r("minilm", "hybrid"),
        "Híbrido MedCPT": r("medcpt", "hybrid"),
        "Híbrido MedCPT + reranker": r("medcpt", "hybrid", rerank=True),
        "Híbrido MiniLM + reranker": r("minilm", "hybrid", rerank=True),
    }
    results = {}
    for name, retr in configs.items():
        results[name] = evaluate(retr, questions)
        a = results[name]["by_kind"]["all"]
        logger.info(
            "%-28s R@5=%.2f MRR=%.2f (%.2fs/pregunta)",
            name,
            a["R@5"],
            a["MRR"],
            results[name]["secs"],
        )

    kinds = ["all", "paraphrase", "code_name", "spanish"]
    counts = {
        k: sum(1 for q in questions if k == "all" or q["kind"] == k) for k in kinds
    }
    lines = [
        f"# Evaluación de búsqueda — {date.today()}",
        "",
        (
            f"{len(questions)} preguntas sintéticas (eval/golden_set.jsonl), una respuesta correcta "
            "por pregunta, métricas a nivel de documento."
        ),
        "",
        "## Todas las preguntas",
        "",
        "| Configuración | Recall@1 | Recall@5 | Recall@10 | MRR@10 | s/pregunta |",
        "|---|---|---|---|---|---|",
    ]
    for name, res in results.items():
        a = res["by_kind"]["all"]
        lines.append(
            f"| {name} | {a['R@1']:.2f} | {a['R@5']:.2f} | {a['R@10']:.2f} | {a['MRR']:.2f} | {res['secs']:.2f} |"
        )
    lines += [
        "",
        "## Recall@5 por tipo de pregunta",
        "",
        "| Configuración | " + " | ".join(f"{k} (n={counts[k]})" for k in kinds) + " |",
        "|---" * (len(kinds) + 1) + "|",
    ]
    for name, res in results.items():
        lines.append(
            f"| {name} | "
            + " | ".join(f"{res['by_kind'][k]['R@5']:.2f}" for k in kinds)
            + " |"
        )
    out = Path("eval/reports") / f"retrieval_{date.today()}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    main()
