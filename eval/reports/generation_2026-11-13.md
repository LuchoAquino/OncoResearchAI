# Evaluación de respuestas del agente — 2026-11-13

12 preguntas escritas a mano (en `evaluation/generation_eval.py`).

| Métrica | Valor |
|---|---|
| Ruta correcta | 100% |
| Respuestas con ≥1 cita | 100% |
| Sin citas inventadas | 100% |
| Sin números sin respaldo | 92% |
| Acierto en preguntas con respuesta conocida (n=4) | 100% |
| Fidelidad media (LLM juez) | 84% |
| Pertinencia media (1-5, LLM juez) | 4.67 |
| Segundos por respuesta (media) | 3.62 |

## Detalle por pregunta

| Pregunta | Ruta | Citas | Fidelidad | Pertinencia | Correcta | Afirmaciones sin respaldo (juez) |
|---|---|---|---|---|---|---|
| ¿Cuántos ensayos clínicos de fase 3 con pembrolizumab están reclutando actualmente? | sql | 1 | 1.00 | 5 | sí | — |
| How many clinical trials of the tracked drugs are sponsored by Pierre Fabre? | sql | 1 | 1.00 | 5 | sí | — |
| ¿Qué fármaco anti-PD-1 tiene más ensayos de fase 3 y cuántos? | sql | 1 | 1.00 | 5 | sí | — |
| List the active phase 3 trials that include relatlimab. | sql | 1 | 0.29 | 3 | sí | NCT06624644 – A Trial of LNS8801 With or Without Pembrolizumab in Patients With Refractory Melanoma; NCT06743126 – SUPRAME‑ACTengine® IMA203 vs. Investigator's Choice of Treatment in Previously Treated, Unresectable or M |
| What are the main mechanisms of resistance to BRAF inhibitors in melanoma? | search | 8 | 1.00 | 5 | — | — |
| ¿Qué resultados de supervivencia mostró el ensayo COLUMBUS con encorafenib y binimetinib? | search | 1 | 0.33 | 4 | — | pero los documentos citados no incluyen datos de supervivencia (ni de supervivencia global ni de supervivencia libre de progresión) [S1].; Sin esa información en los documentos proporcionados, no es posible describir los |
| What adverse reactions are listed in the FDA label of Braftovi? | search | 1 | 1.00 | 5 | — | — |
| ¿Cuál es la dosis recomendada de dabrafenib según su ficha técnica? | search | 1 | 0.50 | 4 | — | La ficha técnica no contiene la dosis inicial estándar de dabrafenib |
| What is known about relatlimab plus nivolumab efficacy in previously untreated melanoma? | search | 6 | 1.00 | 5 | — | — |
| ¿Qué toxicidades inmunorrelacionadas se describen con ipilimumab más nivolumab? | search | 1 | 1.00 | 5 | — | — |
| ¿Qué ensayos de fase 3 con relatlimab están activos y qué evalúan? | both | 4 | 1.00 | 5 | — | — |
| Which recruiting trials combine a BRAF inhibitor with a MEK inhibitor, and what do they test? | both | 1 | 1.00 | 5 | — | — |
