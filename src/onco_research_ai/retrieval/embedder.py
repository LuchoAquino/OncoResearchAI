"""Convierte textos en vectores con modelos de Hugging Face.

Dos familias:
- sentence-transformers (MiniLM, bge-m3): un solo modelo para documentos y preguntas.
- MedCPT (NCBI): DOS modelos entrenados juntos, uno para artículos y otro para preguntas.
"""

import numpy as np
import torch
from sentence_transformers import SentenceTransformer
from transformers import AutoModel, AutoTokenizer

# Nombre corto -> modelo (el de documentos). Se añaden aquí los que queramos comparar.
MODELS = {
    "minilm": "sentence-transformers/all-MiniLM-L6-v2",  # 384 dim, límite 256 tokens, rápido
    "bge-m3": "BAAI/bge-m3",  # 1024 dim, hasta 8192 tokens, ~570M parámetros (lento: ~100 min)
    "medcpt": "ncbi/MedCPT-Article-Encoder",  # 768 dim, biomédico (PubMed), ~110M parámetros
}
MEDCPT_QUERY = "ncbi/MedCPT-Query-Encoder"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class Embedder:
    def __init__(self, key: str):
        self.key = key
        self.is_medcpt = key == "medcpt"
        if self.is_medcpt:
            self.tokenizer = AutoTokenizer.from_pretrained(MODELS[key])
            self.model = self._load(MODELS[key])
            self.query_tokenizer = AutoTokenizer.from_pretrained(MEDCPT_QUERY)
            self.query_model = self._load(MEDCPT_QUERY)
            self.dim = self.model.config.hidden_size
        else:
            self.model = SentenceTransformer(MODELS[key], device=DEVICE)
            if DEVICE == "cuda":
                self.model.half()  # fp16: mitad de memoria, cabe en 4 GB de VRAM
            self.model.max_seq_length = min(self.model.max_seq_length, 512)
            self.tokenizer = self.model.tokenizer
            self.dim = self.model.get_sentence_embedding_dimension()

    @staticmethod
    def _load(name: str):
        model = AutoModel.from_pretrained(name).eval().to(DEVICE)
        return model.half() if DEVICE == "cuda" else model

    def _medcpt(self, tok, model, texts, batch_size, max_length) -> np.ndarray:
        # Ordenar por longitud evita rellenar (padding) textos cortos hasta el tamaño del más largo.
        order = np.argsort([len(t) for t in texts])
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i in range(0, len(texts), batch_size):
            idx = order[i : i + batch_size]
            batch = tok(
                [texts[j] for j in idx],
                truncation=True,
                padding=True,
                max_length=max_length,
                return_tensors="pt",
            ).to(DEVICE)
            with torch.inference_mode():
                cls = model(**batch).last_hidden_state[
                    :, 0, :
                ]  # el vector del token [CLS]
            out[idx] = torch.nn.functional.normalize(cls.float(), dim=-1).cpu().numpy()
        return out

    def encode(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Vectores de DOCUMENTOS (los trozos que se guardan en Qdrant)."""
        if self.is_medcpt:
            return self._medcpt(self.tokenizer, self.model, texts, batch_size, 512)
        # normalize_embeddings: vectores de longitud 1, así coseno == producto escalar
        return self.model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )

    def encode_queries(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        """Vectores de PREGUNTAS. En MedCPT es otro modelo; en los demás, el mismo."""
        if self.is_medcpt:
            return self._medcpt(
                self.query_tokenizer, self.query_model, texts, batch_size, 64
            )
        return self.encode(texts, batch_size)


def chunk_token_counter():
    """Contador de tokens para TROCEAR, igual para todos los modelos.

    Si cada modelo troceara con su propio tokenizador, cada colección tendría trozos distintos
    y la comparación de modelos no sería justa. Se usa el de MiniLM (el más restrictivo: 256
    tokens), y como los trozos son de ≤180, caben holgadamente en los demás modelos.
    """
    tok = AutoTokenizer.from_pretrained(MODELS["minilm"])
    return lambda text: len(tok(text, add_special_tokens=False)["input_ids"])
