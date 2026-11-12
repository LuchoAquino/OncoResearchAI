"""Evalúa las RESPUESTAS del agente (no solo la búsqueda).

Métricas automáticas (sin LLM):
- ruta correcta: ¿eligió SQL / búsqueda / ambos como se esperaba?
- citas válidas: ninguna cita a una fuente inexistente.
- números con respaldo: todos los números de la respuesta aparecen en las fuentes.
- acierto (solo preguntas con respuesta conocida): la respuesta contiene el dato de referencia,
  calculado con SQL escrito a mano.
LLM como juez (fidelidad): otro LLM descompone la respuesta en afirmaciones y comprueba cuántas
están respaldadas por las fuentes que vio el agente. Sesgo conocido: el juez es el mismo modelo
que el generador, así que tiende a ser indulgente; es una señal, no la verdad.
"""

import json
import logging
import time
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from onco_research_ai.agent.graph import ask
from onco_research_ai.llm.client import complete_json

logger = logging.getLogger(__name__)

QUESTIONS = [
    # (pregunta, ruta esperada, textos que deben aparecer: basta con uno de cada lista interna)
    (
        "¿Cuántos ensayos clínicos de fase 3 con pembrolizumab están reclutando actualmente?",
        "sql",
        [["8"]],
    ),
    (
        "How many clinical trials of the tracked drugs are sponsored by Pierre Fabre?",
        "sql",
        [["8"]],
    ),
    (
        "¿Qué fármaco anti-PD-1 tiene más ensayos de fase 3 y cuántos?",
        "sql",
        [["nivolumab"], ["41"]],
    ),
    (
        "List the active phase 3 trials that include relatlimab.",
        "sql",
        [
            [
                "NCT05625399",
                "NCT06624644",
                "NCT06743126",
                "NCT06112314",
                "NCT06264180",
                "NCT06246916",
                "NCT03470922",
            ]
        ],
    ),
    (
        "What are the main mechanisms of resistance to BRAF inhibitors in melanoma?",
        "search",
        [],
    ),
    (
        "¿Qué resultados de supervivencia mostró el ensayo COLUMBUS con encorafenib y binimetinib?",
        "search",
        [],
    ),
    ("What adverse reactions are listed in the FDA label of Braftovi?", "search", []),
    (
        "¿Cuál es la dosis recomendada de dabrafenib según su ficha técnica?",
        "search",
        [],
    ),
    (
        "What is known about relatlimab plus nivolumab efficacy in previously untreated melanoma?",
        "search",
        [],
    ),
    (
        "¿Qué toxicidades inmunorrelacionadas se describen con ipilimumab más nivolumab?",
        "search",
        [],
    ),
    ("¿Qué ensayos de fase 3 con relatlimab están activos y qué evalúan?", "both", []),
    (
        "Which recruiting trials combine a BRAF inhibitor with a MEK inhibitor, and what do they test?",
        "both",
        [],
    ),
]


class Judgement(BaseModel):
    claims_total: int
    claims_supported: int
    unsupported_claims: list[str]
    relevance: int  # 1-5


JUDGE_PROMPT = """You are a strict fact-checker. Below are the SOURCES an assistant was given and
its ANSWER. Split the answer into atomic factual claims (ignore headings and phrases like
"according to the sources"). A claim is supported only if the sources state it (or it follows
directly). Also rate relevance 1-5: does the answer address the question?
Reply JSON: {"claims_total": int, "claims_supported": int, "unsupported_claims": [str],
"relevance": int}

QUESTION: {q}

SOURCES:
{ctx}

ANSWER:
{a}"""


def main() -> None:
    rows = []
    for q, expected_route, must in QUESTIONS:
        out = ask(q)
        c = out["check"]
        correct = None
        if must:
            correct = all(
                any(m.lower() in out["answer"].lower() for m in group) for group in must
            )
        judge = complete_json(
            [
                {
                    "role": "user",
                    "content": JUDGE_PROMPT.replace("{q}", q)
                    .replace("{ctx}", out["context"][:9000])
                    .replace("{a}", out["answer"]),
                }
            ],
            Judgement,
        )
        rows.append(
            {
                "question": q,
                "route": out["route"],
                "route_ok": out["route"] == expected_route,
                "n_cited": len(c["cited"]),
                "invalid": c["invalid"],
                "unsupported_numbers": c["unsupported_numbers"],
                "correct": correct,
                "faithfulness": judge.claims_supported / judge.claims_total
                if judge.claims_total
                else 1.0,
                "unsupported_claims": judge.unsupported_claims,
                "relevance": judge.relevance,
                "attempts": out["attempts"],
                "secs": out["timings"]["total"],
                "answer": out["answer"],
            }
        )
        r = rows[-1]
        logger.info(
            "ruta=%s(%s) citas=%d fidelidad=%.2f relev=%d correcto=%s | %s",
            r["route"],
            "ok" if r["route_ok"] else "MAL",
            r["n_cited"],
            r["faithfulness"],
            r["relevance"],
            r["correct"],
            q[:60],
        )
        time.sleep(25)  # cuota: 8 000 tokens/minuto

    n = len(rows)
    graded = [r for r in rows if r["correct"] is not None]
    summary = {
        "Ruta correcta": sum(r["route_ok"] for r in rows) / n,
        "Respuestas con ≥1 cita": sum(r["n_cited"] > 0 for r in rows) / n,
        "Sin citas inventadas": sum(not r["invalid"] for r in rows) / n,
        "Sin números sin respaldo": sum(not r["unsupported_numbers"] for r in rows) / n,
        f"Acierto en preguntas con respuesta conocida (n={len(graded)})": sum(
            r["correct"] for r in graded
        )
        / len(graded),
        "Fidelidad media (LLM juez)": sum(r["faithfulness"] for r in rows) / n,
        "Pertinencia media (1-5, LLM juez)": sum(r["relevance"] for r in rows) / n,
        "Segundos por respuesta (media)": sum(r["secs"] for r in rows) / n,
    }
    lines = [
        f"# Evaluación de respuestas del agente — {date.today()}",
        "",
        f"{n} preguntas escritas a mano (en `evaluation/generation_eval.py`).",
        "",
        "| Métrica | Valor |",
        "|---|---|",
    ]
    for k, v in summary.items():
        lines.append(
            f"| {k} | {v:.2f} |"
            if "Segundos" in k or "1-5" in k
            else f"| {k} | {v:.0%} |"
        )
    lines += [
        "",
        "## Detalle por pregunta",
        "",
        "| Pregunta | Ruta | Citas | Fidelidad | Pertinencia | Correcta | Afirmaciones sin respaldo (juez) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        unsup = "; ".join(r["unsupported_claims"])[:220].replace("|", "/") or "—"
        corr = "—" if r["correct"] is None else ("sí" if r["correct"] else "**no**")
        route = r["route"] + ("" if r["route_ok"] else " (**esperada otra**)")
        lines.append(
            f"| {r['question']} | {route} | {r['n_cited']} | {r['faithfulness']:.2f} | "
            f"{r['relevance']} | {corr} | {unsup} |"
        )
    out_dir = Path("eval/reports")
    (out_dir / f"generation_{date.today()}.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    (out_dir / f"generation_{date.today()}.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    main()
