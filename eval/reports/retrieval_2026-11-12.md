# Evaluación de búsqueda — 2026-11-12

102 preguntas sintéticas (eval/golden_set.jsonl), una respuesta correcta por pregunta, métricas a nivel de documento.

## Todas las preguntas

| Configuración | Recall@1 | Recall@5 | Recall@10 | MRR@10 | s/pregunta |
|---|---|---|---|---|---|
| BM25 (palabras) | 0.54 | 0.72 | 0.79 | 0.63 | 0.11 |
| Denso MiniLM | 0.62 | 0.81 | 0.81 | 0.70 | 0.02 |
| Denso MedCPT | 0.27 | 0.50 | 0.61 | 0.37 | 0.03 |
| Híbrido MiniLM | 0.65 | 0.84 | 0.86 | 0.73 | 0.12 |
| Híbrido MedCPT | 0.55 | 0.74 | 0.76 | 0.62 | 0.15 |
| Híbrido MedCPT + reranker | 0.72 | 0.81 | 0.83 | 0.76 | 2.18 |
| Híbrido MiniLM + reranker | 0.75 | 0.87 | 0.88 | 0.80 | 2.13 |

## Recall@5 por tipo de pregunta

| Configuración | all (n=102) | paraphrase (n=42) | code_name (n=18) | spanish (n=42) |
|---|---|---|---|---|
| BM25 (palabras) | 0.72 | 0.98 | 0.67 | 0.48 |
| Denso MiniLM | 0.81 | 0.98 | 0.83 | 0.64 |
| Denso MedCPT | 0.50 | 0.71 | 0.56 | 0.26 |
| Híbrido MiniLM | 0.84 | 0.98 | 0.94 | 0.67 |
| Híbrido MedCPT | 0.74 | 0.90 | 0.89 | 0.50 |
| Híbrido MedCPT + reranker | 0.81 | 0.98 | 0.83 | 0.64 |
| Híbrido MiniLM + reranker | 0.87 | 0.98 | 0.94 | 0.74 |
