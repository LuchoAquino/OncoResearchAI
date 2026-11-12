"""Convierte textos en vectores con un modelo de Hugging Face (sentence-transformers)."""

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

# Nombre corto -> modelo. Se añaden aquí los que queramos comparar en la Fase 5.
MODELS = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",  # 384 dim, límite 256 tokens, rápido
    "bge-m3": "BAAI/bge-m3",  # 1024 dim, hasta 8192 tokens, multilingüe, ~570M parámetros
}


class Embedder:
    def __init__(self, key: str):
        self.key = key
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(MODELS[key], device=device)
        if device == "cuda":
            self.model.half()  # fp16: mitad de memoria, cabe en 4 GB de VRAM
        self.model.max_seq_length = min(self.model.max_seq_length, 512)
        self.dim = self.model.get_sentence_embedding_dimension()

    @property
    def tokenizer(self):
        return self.model.tokenizer

    def count_tokens(self, text: str) -> int:
        return len(self.tokenizer(text, add_special_tokens=False)["input_ids"])

    def encode(
        self, texts: list[str], batch_size: int = 64, progress: bool = False
    ) -> np.ndarray:
        # normalize_embeddings: vectores de longitud 1, así coseno == producto escalar
        return self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=progress,
        )


def chunk_token_counter():
    """Contador de tokens para TROCEAR, igual para todos los modelos.

    Si cada modelo troceara con su propio tokenizador, cada colección tendría trozos distintos
    y la comparación de modelos no sería justa. Se usa el de MiniLM (el más restrictivo: 256
    tokens), y como los trozos son de ≤180, caben holgadamente en bge-m3 (hasta 8 192).
    """
    tok = AutoTokenizer.from_pretrained(MODELS["minilm"])
    return lambda text: len(tok(text, add_special_tokens=False)["input_ids"])
