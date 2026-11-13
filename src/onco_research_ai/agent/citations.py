"""Fuentes numeradas [S1..Sn] para el LLM y comprobación de las citas de su respuesta.

El LLM solo ve las fuentes que le damos y debe citar cada afirmación. Después se comprueba:
- citas inválidas: [S9] cuando solo había 6 fuentes (el modelo inventó una fuente);
- frases sin cita: afirmaciones que no se pueden rastrear.
"""

import re
from dataclasses import asdict, dataclass

from onco_research_ai.processing.extractor import numbers_in
from onco_research_ai.retrieval.hybrid import Hit

# Una cita es cualquier S1 o SQL dentro de corchetes: [S1], [S1, S3], [SQL; S2]...
BRACKET = re.compile(r"\[([^\[\]]{1,40})\]")
REF = re.compile(r"\b(S\d+|SQL)\b")


def refs_in(text: str) -> list[str]:
    return [r for group in BRACKET.findall(text) for r in REF.findall(group)]


def malformed_refs(text: str) -> list[str]:
    """Citas con forma de cita pero mal escritas: [V5], [A3], [S]... (el modelo se equivocó de letra)."""
    out = []
    for group in BRACKET.findall(text):
        for token in re.split(r"[,;/\s]+", group.strip()):
            if re.fullmatch(r"[A-Za-z]{1,3}\d{1,3}", token) and not re.fullmatch(
                r"S\d+", token
            ):
                out.append(token)
    return out


def strip_citations(text: str) -> str:
    return BRACKET.sub(lambda m: " " if REF.search(m.group(1)) else m.group(0), text)


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

    Cada número se acepta si ALGUNA de sus lecturas está en las fuentes: "1,5" puede ser
    1.5 (decimal en español) o 15 (separador de miles en inglés). Se ignoran las referencias
    [S3] y los enteros de una cifra (numeración, "fase 3").
    """
    in_context = numbers_in(context)
    bad = set()
    for tok in re.findall(r"\d+(?:[.,]\d+)*", strip_citations(answer)):
        readings = {tok.replace(",", "").rstrip("."), tok.replace(",", ".")}
        if not readings & in_context and not (tok.isdigit() and len(tok) == 1):
            bad.add(tok)
    return sorted(bad)


def check_citations(
    answer: str, sources: list[Source], has_sql: bool, context: str = ""
) -> dict:
    valid = {s.ref for s in sources} | ({"SQL"} if has_sql else set())
    cited = refs_in(answer)
    # Inválidas: citas a fuentes que no existen ([S9] con 6 fuentes) o mal escritas ([V5]).
    invalid = sorted({c for c in cited if c not in valid} | set(malformed_refs(answer)))
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+|\n+", answer)
        if len(s.strip()) > 40
        # títulos, filas de tabla y notas aclaratorias no son afirmaciones
        and not s.strip().startswith(("#", "|", "*Nota", "Nota"))
        and not s.strip().endswith(":")
    ]
    uncited = [s for s in sentences if not refs_in(s)]
    return {
        "cited": sorted(set(cited) & valid, key=lambda r: (r == "SQL", r)),
        "invalid": invalid,
        "uncited_sentences": uncited,
        "n_sentences": len(sentences),
        "unsupported_numbers": unsupported_numbers(answer, context) if context else [],
    }
