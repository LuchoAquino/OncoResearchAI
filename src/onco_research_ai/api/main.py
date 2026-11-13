"""API REST (FastAPI). Documentación interactiva en http://localhost:8000/docs

uv run uvicorn onco_research_ai.api.main:app --port 8000
"""

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from onco_research_ai.logging_config import setup_logging
from onco_research_ai.storage import queries, vectorstore

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="OncoResearchAI",
    description="Veille concurrentielle en melanoma: ensayos, artículos y fichas FDA con búsqueda "
    "híbrida y un agente que responde citando sus fuentes.",
    version="1.0.0",
)

Source = Literal["trial", "publication", "label", "congress"]
Phase = Literal["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]


class SearchRequest(BaseModel):
    query: str = Field(
        ..., min_length=2, examples=["resistance mechanisms to BRAF inhibitors"]
    )
    k: int = Field(8, ge=1, le=30)
    source: Source | None = None
    drug: str | None = Field(None, examples=["encorafenib"])
    phase: Phase | None = None


class AskRequest(BaseModel):
    question: str = Field(
        ..., min_length=3, examples=["¿Qué ensayos de fase 3 hay con encorafenib?"]
    )
    model: Literal["groq", "gemini", "local"] | None = Field(
        None, description="LLM to use. Default: groq. See GET /models."
    )


@app.get("/health")
def health() -> dict:
    """Comprueba Postgres y Qdrant."""
    out = {"postgres": queries.health()}
    client = vectorstore.get_client()
    out["qdrant"] = {
        c.name: client.count(c.name).count for c in client.get_collections().collections
    }
    return out


@app.post("/search")
def search(req: SearchRequest) -> list[dict]:
    """Búsqueda híbrida (BM25 + vectores + reranker). Devuelve un trozo por documento."""
    from onco_research_ai.agent.graph import (
        get_retriever,
    )  # carga los modelos solo al usarse

    drug = queries.resolve_drug(req.drug) if req.drug else None
    if req.drug and not drug:
        raise HTTPException(404, f"Unknown drug: {req.drug}")
    hits = get_retriever().search(
        req.query, k=req.k, source=req.source, drugs=drug, phases=req.phase
    )
    return [{"score": round(h.score, 3), **h.payload} for h in hits]


@app.get("/models")
def models() -> list[dict]:
    """The selectable LLMs, whether each is available now, and how much each has been used."""
    from onco_research_ai.llm.client import models_status

    return models_status()


@app.post("/ask")
def ask(req: AskRequest) -> dict:
    """Agente: decide entre SQL y búsqueda, responde citando y verifica sus citas."""
    from onco_research_ai.agent.graph import ask as agent_ask

    return agent_ask(req.question, req.model)


@app.get("/drugs")
def drugs() -> list[dict]:
    return queries.list_drugs()


@app.get("/drugs/{name}")
def drug(name: str) -> dict:
    """Perfil de un fármaco. Acepta nombre genérico, marca o código (Keytruda, MK-3475...)."""
    profile = queries.drug_profile(name)
    if profile is None:
        raise HTTPException(404, f"Unknown drug: {name}")
    return profile


@app.get("/trials")
def trials(
    drug: str | None = None,
    mechanism: Literal[
        "BRAF inhibitor", "MEK inhibitor", "anti-PD-1", "anti-CTLA-4", "anti-LAG-3"
    ]
    | None = None,
    phase: Phase | None = None,
    status: str | None = None,
    sponsor_class: str | None = None,
    active_only: bool = False,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    return queries.list_trials(
        drug, mechanism, phase, status, sponsor_class, active_only, limit
    )


@app.get("/landscape")
def landscape() -> dict:
    """Panorama competitivo: ensayos por fármaco y fase, activos, por año y patrocinadores."""
    return queries.landscape()
