"""Agente con LangGraph: decide cómo buscar, busca, responde citando y comprueba sus citas.

    plan ──► sql? ──► search? ──► generate ──► verify ──► fin
                                     ▲            │
                                     └────────────┘  (1 reintento si faltan citas)

- plan: el LLM clasifica la pregunta (datos exactos -> SQL; contenido -> búsqueda; o ambos),
  la traduce al inglés para buscar (los modelos de embeddings son de inglés) y extrae filtros.
- sql: texto -> SQL seguro (agent/sql_tool.py).
- search: búsqueda híbrida + reranker (retrieval/hybrid.py), con filtros si los hay.
- generate: responde SOLO con las fuentes, citando [S1], [SQL]...
- verify: comprueba que las citas existen y que las afirmaciones están citadas.
"""

import logging
import time
from typing import Literal, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel

from onco_research_ai.agent.citations import (
    Source,
    check_citations,
    format_context,
    sources_from_hits,
)
from onco_research_ai.agent.sql_tool import SQLResult, run_sql_tool
from onco_research_ai.llm.client import complete, complete_json
from onco_research_ai.processing.drugs_seed import SEED
from onco_research_ai.retrieval.hybrid import Retriever

logger = logging.getLogger(__name__)
_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    global _retriever
    if _retriever is None:
        _retriever = Retriever()  # se carga una vez (modelos en GPU)
    return _retriever


class Plan(BaseModel):
    route: Literal["sql", "search", "both"]
    search_query: str  # en inglés
    drug: str | None = None
    source: Literal["trial", "publication", "label", "congress"] | None = None
    phase: Literal["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4"] | None = None


class State(TypedDict, total=False):
    question: str
    plan: dict
    sql: dict
    sources: list[dict]
    answer: str
    check: dict
    context: str
    attempts: int
    timings: dict


PLAN_PROMPT = f"""You route questions for a melanoma competitive-intelligence assistant.
Data: clinical trials (ClinicalTrials.gov), scientific abstracts (Europe PMC), FDA drug labels,
congress PDFs. Linked drugs: {", ".join(SEED)}.

Return JSON with:
- route: "sql" for counts, lists, rankings or filters over structured fields (phase, status,
  sponsor, dates, number of trials/articles); "search" for content questions (results, mechanisms,
  safety, dosing, evidence); "both" when a list/count AND content are needed.
- search_query: an English search query capturing the content need (translate if needed).
- drug: one of the linked drugs (lowercase INN) if the question is about exactly one of them, else null.
  Map brand names/codes to the INN (Keytruda/MK-3475 -> pembrolizumab, Braftovi -> encorafenib...).
- source: "trial" | "publication" | "label" | "congress" only if the user clearly wants that type, else null.
- phase: e.g. "PHASE3" only if the user asks for a specific trial phase, else null."""

ANSWER_PROMPT = """You are an assistant for pharmaceutical competitive intelligence in melanoma.
Answer the question using ONLY the sources below ([S1], [S2]... are documents; [SQL] is a
database query result). Rules:
- Answer in the SAME LANGUAGE as the question.
- Every factual sentence must end with its citation(s), e.g. "... improved PFS [S2]." or "[SQL]".
- Never cite a source that is not listed. Never use outside knowledge for facts or numbers.
- Do NOT compute new numbers (totals, sums, averages) that are not explicitly in the sources;
  report the numbers as given (a trial can appear in several SQL rows).
- If the sources do not answer the question, say so clearly and say what is missing.
- Be concise: a short direct answer first, then bullet points with the key evidence."""


def plan_node(state: State) -> State:
    t = time.time()
    try:
        plan = complete_json(
            [
                {"role": "system", "content": PLAN_PROMPT},
                {"role": "user", "content": state["question"]},
            ],
            Plan,
        )
        if plan.drug and plan.drug not in SEED:
            plan.drug = None
    except Exception as exc:  # noqa: BLE001  — si el router falla, se busca sin filtros
        logger.warning("plan falló (%s); se usa búsqueda simple", exc)
        plan = Plan(route="search", search_query=state["question"])
    return {
        "plan": plan.model_dump(),
        "attempts": 0,
        "timings": {"plan": time.time() - t},
    }


def sql_node(state: State) -> State:
    t = time.time()
    res: SQLResult = run_sql_tool(state["question"])
    return {
        "sql": res.__dict__,
        "timings": {**state["timings"], "sql": time.time() - t},
    }


def search_node(state: State) -> State:
    t = time.time()
    p = state["plan"]
    filters = {
        "drugs": p.get("drug"),
        "source": p.get("source"),
        "phases": p.get("phase"),
    }
    retriever = get_retriever()
    hits = retriever.search(p["search_query"], k=8, **filters)
    if len(hits) < 3 and any(
        filters.values()
    ):  # filtros demasiado estrictos: se relajan
        hits = retriever.search(p["search_query"], k=8)
    sources = [s.to_dict() for s in sources_from_hits(hits)]
    return {
        "sources": sources,
        "timings": {**state["timings"], "search": time.time() - t},
    }


def generate_node(state: State) -> State:
    t = time.time()
    sources = [Source(**s) for s in state.get("sources", [])]
    parts = []
    if sql := state.get("sql"):
        parts.append("[SQL]\n" + SQLResult(**sql).as_text())
    if sources:
        parts.append(format_context(sources))
    context = "\n\n".join(parts) or "(no sources found)"
    messages = [
        {"role": "system", "content": ANSWER_PROMPT},
        {
            "role": "user",
            "content": f"Sources:\n{context}\n\nQuestion: {state['question']}",
        },
    ]
    if state.get("attempts", 0) > 0:  # reintento: se le dice exactamente qué falló
        c = state["check"]
        problems = []
        if c["invalid"] or c["uncited_sentences"]:
            problems.append("some sentences were uncited or cited non-existent sources")
        if c["unsupported_numbers"]:
            problems.append(
                "these numbers do not appear in the sources: "
                + ", ".join(c["unsupported_numbers"])
                + " (remove them; do not compute, add up or round numbers)"
            )
        messages += [
            {"role": "assistant", "content": state["answer"]},
            {
                "role": "user",
                "content": "Rewrite your answer. Problems: "
                + "; ".join(problems)
                + ". Every factual sentence must cite a listed source.",
            },
        ]
    answer = complete(messages, temperature=0.1)
    return {
        "answer": answer,
        "context": context,
        "attempts": state.get("attempts", 0) + 1,
        "timings": {**state["timings"], "generate": time.time() - t},
    }


def verify_node(state: State) -> State:
    sources = [Source(**s) for s in state.get("sources", [])]
    sql_ok = bool(state.get("sql")) and not state["sql"].get("error")
    return {
        "check": check_citations(
            state["answer"], sources, has_sql=sql_ok, context=state["context"]
        )
    }


def after_verify(state: State) -> str:
    c = state["check"]
    needs_retry = (
        c["invalid"]
        or c["unsupported_numbers"]
        or (c["n_sentences"] and len(c["uncited_sentences"]) > c["n_sentences"] / 2)
    )
    has_evidence = state.get("sources") or state.get("sql")
    return "generate" if needs_retry and has_evidence and state["attempts"] < 2 else END


def build_graph():
    g = StateGraph(State)
    g.add_node("plan", plan_node)
    g.add_node("sql", sql_node)
    g.add_node("search", search_node)
    g.add_node("generate", generate_node)
    g.add_node("verify", verify_node)
    g.set_entry_point("plan")
    g.add_conditional_edges(
        "plan",
        lambda s: "search" if s["plan"]["route"] == "search" else "sql",
        ["sql", "search"],
    )
    g.add_conditional_edges(
        "sql",
        lambda s: "search" if s["plan"]["route"] == "both" else "generate",
        ["search", "generate"],
    )
    g.add_edge("search", "generate")
    g.add_edge("generate", "verify")
    g.add_conditional_edges("verify", after_verify, ["generate", END])
    return g.compile()


_graph = None


def ask(question: str) -> dict:
    """Punto de entrada: pregunta -> respuesta con fuentes, SQL usado y comprobación de citas."""
    global _graph
    if _graph is None:
        _graph = build_graph()
    t = time.time()
    state = _graph.invoke({"question": question})
    cited = set(state.get("check", {}).get("cited", []))
    sources = state.get("sources", [])
    return {
        "question": question,
        "answer": state.get("answer", ""),
        "route": state["plan"]["route"],
        "plan": state["plan"],
        "sql": state.get("sql"),
        "sources": sources,
        "cited_sources": [s for s in sources if s["ref"] in cited],
        "check": state.get("check", {}),
        "attempts": state.get("attempts", 0),
        "timings": {**state.get("timings", {}), "total": time.time() - t},
    }


if __name__ == "__main__":
    import json
    import sys

    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    out = ask(" ".join(sys.argv[1:]) or "What are the phase 3 trials of encorafenib?")
    print(out["answer"])
    print(
        json.dumps(
            {k: out[k] for k in ("route", "plan", "check", "timings")},
            indent=1,
            ensure_ascii=False,
        )
    )
