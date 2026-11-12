"""Fuentes numeradas [S1..Sn] para el LLM y comprobación de las citas de su respuesta.

El LLM solo ve las fuentes que le damos y debe citar cada afirmación. Después se comprueba:
- citas inválidas: [S9] cuando solo había 6 fuentes (el modelo inventó una fuente);
- frases sin cita: afirmaciones que no se pueden rastrear.
"""

import re
from dataclasses import asdict, dataclass

from onco_research_ai.processing.extractor import numbers_in
from onco_research_ai.retrieval.hybrid import Hit

CITE = re.compile(r"\[(S\d+|SQL)\]")
SOURCE_LABEL = {
    "trial": "Ensayo clínico (ClinicalTrials.gov)",
    "publication": "Artículo (Europe PMC)",
    "label": "Ficha técnica FDA",
    "congress": "Documento de congreso (PDF)",
}


@dataclass
class Source:
    ref: str  # "S1"
    doc_id: str
    source: str
    title: str
    url: str
    text: str
    year: int | None = None
    page: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def sources_from_hits(hits: list[Hit]) -> list[Source]:
    return [
        Source(
            ref=f"S{i}",
            doc_id=h.doc_id,
            source=h.payload["source"],
            title=h.payload.get("title", ""),
            url=h.payload.get("url", ""),
            text=h.payload["text"],
            year=h.payload.get("year"),
            page=h.payload.get("page"),
        )
        for i, h in enumerate(hits, 1)
    ]


def format_context(sources: list[Source]) -> str:
    blocks = []
    for s in sources:
        meta = f"{SOURCE_LABEL.get(s.source, s.source)}, {s.year or 's/f'}"
        if s.page:
            meta += f", p. {s.page}"
        blocks.append(f"[{s.ref}] {s.title} ({meta})\n{s.text}")
    return "\n\n".join(blocks)


def unsupported_numbers(answer: str, context: str) -> list[str]:
    """Números de la respuesta que no aparecen en ninguna fuente (inventados o calculados).

    Se ignoran las referencias [S3] y los enteros de una cifra (numeración, "fase 3").
    """
    in_context = numbers_in(context)
    found = numbers_in(CITE.sub(" ", answer))
    return sorted(
        n for n in found if n not in in_context and not (n.isdigit() and len(n) == 1)
    )


def check_citations(
    answer: str, sources: list[Source], has_sql: bool, context: str = ""
) -> dict:
    valid = {s.ref for s in sources} | ({"SQL"} if has_sql else set())
    cited = CITE.findall(answer)
    invalid = sorted({c for c in cited if c not in valid})
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", answer)
        if len(s.strip()) > 40
        and not s.strip().startswith("#")
        and not s.strip().endswith(":")
    ]
    uncited = [s for s in sentences if not CITE.search(s)]
    return {
        "cited": sorted(set(cited) & valid, key=lambda r: (r == "SQL", r)),
        "invalid": invalid,
        "uncited_sentences": uncited,
        "n_sentences": len(sentences),
        "unsupported_numbers": unsupported_numbers(answer, context) if context else [],
    }
