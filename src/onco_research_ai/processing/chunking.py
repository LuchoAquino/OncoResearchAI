"""Trocear textos largos en fragmentos ("chunks") que quepan en el modelo de embeddings.

Por qué trocear: (1) los modelos leen un máximo de tokens y descartan el resto sin avisar;
(2) un vector para 400 tokens mezcla varias ideas y busca peor que uno por idea.
Se corta SIEMPRE entre frases, con 1 frase de solapamiento para no perder el hilo.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

# Corta tras . ! ? si la siguiente frase empieza con mayúscula, número o corchete.
# Imperfecto ("vs. Placebo", "et al. Se") pero suficiente para abstracts.
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\[(])")


@dataclass
class Chunk:
    doc_id: str  # id del documento de origen (NCT, id de artículo, set_id)
    index: int  # nº de trozo dentro del documento
    text: str  # lo que se convierte en vector
    payload: dict = field(default_factory=dict)  # metadatos para filtrar y citar

    @property
    def point_id(self) -> str:
        """Id determinista: re-indexar el mismo trozo lo sobrescribe en vez de duplicarlo."""
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{self.doc_id}#{self.index}"))


def split_text(
    text: str, count: Callable[[str], int], max_tokens: int = 180, overlap: int = 1
) -> list[str]:
    """Agrupa frases hasta ~max_tokens. `count` mide tokens con el tokenizador del modelo."""
    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0
    has_new = (
        False  # ¿hay en `current` alguna frase que aún no esté en un chunk guardado?
    )

    def flush():
        nonlocal current, current_tokens, has_new
        if has_new:
            chunks.append(" ".join(current))
        current = current[-overlap:] if overlap else []
        current_tokens = sum(count(s) for s in current)
        has_new = False

    for sentence in SENTENCE_END.split(text.strip()):
        n = count(sentence)
        if n > max_tokens:  # frase gigante (tablas, listas): se parte por palabras
            flush()
            words, piece = sentence.split(), []
            for w in words:
                if piece and count(" ".join(piece + [w])) > max_tokens:
                    chunks.append(" ".join(piece))
                    piece = []
                piece.append(w)
            if piece:
                chunks.append(" ".join(piece))
            current, current_tokens, has_new = [], 0, False
            continue
        if current and current_tokens + n > max_tokens:
            flush()
        current.append(sentence)
        current_tokens += n
        has_new = True
    if has_new:
        chunks.append(" ".join(current))
    return chunks
