# Evaluación de respuestas del agente — 2026-11-18

12 preguntas escritas a mano (en `evaluation/generation_eval.py`).

| Métrica | Valor |
|---|---|
| Ruta correcta | 100% |
| Respuestas con ≥1 cita | 100% |
| Sin citas inventadas | 100% |
| Sin números sin respaldo | 100% |
| Acierto en preguntas con respuesta conocida (n=4) | 100% |
| Fidelidad media (LLM juez) | 89% |
| Pertinencia media (1-5, LLM juez) | 4.67 |
| Segundos por respuesta (media) | 10.07 |

## Detalle por pregunta

| Pregunta | Ruta | Citas | Fidelidad | Pertinencia | Correcta | Afirmaciones sin respaldo (juez) |
|---|---|---|---|---|---|---|
| ¿Cuántos ensayos clínicos de fase 3 con pembrolizumab están reclutando actualmente? | sql | 1 | 1.00 | 5 | sí | — |
| How many clinical trials of the tracked drugs are sponsored by Bristol-Myers Squibb? | sql | 1 | 1.00 | 5 | sí | — |
| ¿Qué fármaco anti-PD-1 tiene más ensayos de fase 3 y cuántos? | sql | 1 | 1.00 | 5 | sí | — |
| List the active phase 3 trials that include relatlimab. | sql | 1 | 1.00 | 5 | sí | — |
| What are the main mechanisms of resistance to BRAF inhibitors in melanoma? | search | 4 | 0.60 | 5 | — | Activation of alternative survival pathways – up‑regulation of parallel pathways such as PI3K‑AKT, RTK signaling, or other compensatory routes that protect cells from BRAF‑targeted therapy; Microenvironment‑mediated resi |
| ¿Qué resultados de supervivencia mostró el ensayo COLUMBUS con encorafenib y binimetinib? | search | 1 | 0.50 | 4 | — | El ensayo COLUMBUS (Columbus‑AD) no presenta en los documentos citados datos de supervivencia |
| What adverse reactions are listed in the FDA label of Braftovi? | search | 1 | 1.00 | 5 | — | — |
| ¿Cuál es la dosis recomendada de dabrafenib según su ficha técnica? | search | 1 | 0.75 | 2 | — | La ficha técnica de dabrafenib solo detalla las reducciones de dosis que pueden aplicarse y no indica la dosis inicial estándar. |
| What is known about relatlimab plus nivolumab efficacy in previously untreated melanoma? | search | 4 | 1.00 | 5 | — | — |
| ¿Qué toxicidades inmunorrelacionadas se describen con ipilimumab más nivolumab? | search | 2 | 1.00 | 5 | — | — |
| ¿Qué ensayos de fase 3 con relatlimab están activos y qué evalúan? | both | 3 | 0.83 | 5 | — | Un ensayo que prueba múltiples fármacos se contabiliza bajo cada uno de ellos |
| Which recruiting trials combine a BRAF inhibitor with a MEK inhibitor, and what do they test? | both | 1 | 1.00 | 5 | — | — |
