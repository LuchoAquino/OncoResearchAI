"""Construye el conjunto de evaluación de búsqueda (eval/golden_set.jsonl).

Método "known-item": se toma un trozo al azar, el LLM escribe una pregunta que ese trozo
responde, y su documento queda como respuesta correcta. Variantes:
- code_name: la misma pregunta con el código de desarrollo del fármaco (pembrolizumab -> MK-3475).
- spanish:   la misma pregunta en español (los modelos de embeddings son solo de inglés).

Limitaciones (documentadas en el informe): las preguntas son sintéticas, tienen UNA respuesta
correcta (otros documentos igual de válidos cuentan como fallo) y conviene revisarlas a mano.
"""

import json
import logging
import random
import re
import time
from pathlib import Path

from pydantic import BaseModel

from onco_research_ai.llm.client import complete_json
from onco_research_ai.processing.drugs_seed import SEED
from onco_research_ai.retrieval.bm25 import BM25Index

logger = logging.getLogger(__name__)
OUT = Path("eval/golden_set.jsonl")
PER_SOURCE = {"trial": 16, "publication": 18, "label": 8}
SEED_RANDOM = 42


class Generated(BaseModel):
    usable: bool
    question: str
    question_es: str


PROMPT = """You help build an evaluation set for a search engine over melanoma clinical trials,
scientific abstracts and FDA drug labels. Below is ONE passage from the collection.

Write a question that a pharmaceutical competitive-intelligence analyst could ask and that THIS
passage answers specifically (not a generic question many documents would answer).
Rules: paraphrase, do not copy the title; do not mention identifiers (NCT numbers, PMIDs);
keep drug names as written in the passage; one sentence.
Set "usable": false if the passage is too generic, boilerplate or truncated to support a
specific question. Also give the same question translated to Spanish in "question_es".
Reply with JSON: {"usable": bool, "question": str, "question_es": str}

Passage (source: {source}, title: {title}):
{text}"""


def code_variant(question: str) -> str | None:
    for inn, syns in SEED.items():
        if re.search(rf"\b{inn}\b", question, re.IGNORECASE) and syns.get("code"):
            return re.sub(rf"\b{inn}\b", syns["code"][0], question, flags=re.IGNORECASE)
    return None


def build() -> None:
    rng = random.Random(SEED_RANDOM)
    index = BM25Index.load()
    by_source: dict[str, list[dict]] = {}
    for p in index.payloads:
        if len(p["text"]) > 400:  # trozos con algo de contenido
            by_source.setdefault(p["source"], []).append(p)

    items, n = [], 0
    for source, want in PER_SOURCE.items():
        pool = rng.sample(by_source[source], k=min(len(by_source[source]), want * 3))
        used_docs, got = set(), 0
        for p in pool:
            if got == want:
                break
            if p["doc_id"] in used_docs:
                continue
            msg = PROMPT.replace("{source}", source).replace("{title}", p["title"])
            msg = msg.replace("{text}", p["text"][:2500])
            try:
                g = complete_json([{"role": "user", "content": msg}], Generated)
            except Exception as exc:  # noqa: BLE001
                logger.warning("fallo generando pregunta (%s)", exc.__class__.__name__)
                continue
            time.sleep(2)  # cuota gratuita de Groq
            if not g.usable:
                continue
            used_docs.add(p["doc_id"])
            got += 1
            base = {
                "relevant": [p["doc_id"]],
                "source": source,
                "doc_title": p["title"],
            }
            n += 1
            items.append(
                {
                    "id": f"q{n:03d}",
                    "kind": "paraphrase",
                    "question": g.question,
                    **base,
                }
            )
            items.append(
                {
                    "id": f"q{n:03d}-es",
                    "kind": "spanish",
                    "question": g.question_es,
                    **base,
                }
            )
            if variant := code_variant(g.question):
                items.append(
                    {
                        "id": f"q{n:03d}-code",
                        "kind": "code_name",
                        "question": variant,
                        **base,
                    }
                )
        logger.info("%s: %d preguntas", source, got)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n",
        encoding="utf-8",
    )
    logger.info("%d preguntas en %s", len(items), OUT)


def load() -> list[dict]:
    return [
        json.loads(line)
        for line in OUT.read_text(encoding="utf-8").splitlines()
        if line
    ]


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    build()
