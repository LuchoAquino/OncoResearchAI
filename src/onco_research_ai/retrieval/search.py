"""Búsqueda semántica de prueba.

uv run python -m onco_research_ai.retrieval.search "mecanismos de resistencia a BRAF" --drug vemurafenib
"""

import argparse

from onco_research_ai.retrieval.embedder import Embedder
from onco_research_ai.storage import vectorstore

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--model", default="minilm")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--source", choices=["trial", "publication", "label"])
    ap.add_argument("--drug")
    ap.add_argument("--phase", help="p. ej. PHASE3")
    a = ap.parse_args()

    emb = Embedder(a.model)
    hits = vectorstore.search(
        vectorstore.get_client(),
        vectorstore.collection_name(a.model),
        emb.encode([a.query])[0],
        k=a.k,
        source=a.source,
        drugs=a.drug,
        phases=a.phase,
    )
    for h in hits:
        p = h.payload
        print(
            f"{h.score:.3f} [{p['source']}] {p['title'][:90]}\n        {p['text'][:160]}...\n        {p['url']}"
        )
