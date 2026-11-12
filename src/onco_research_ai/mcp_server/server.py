"""Servidor MCP: expone las capacidades del proyecto como herramientas para agentes de IA
(Claude Desktop, Claude Code, MCP Inspector...).

REST vs MCP: una API REST la consume un programa que ya sabe qué endpoint llamar. MCP es un
protocolo para que un AGENTE descubra solo qué herramientas hay (nombre, descripción, parámetros)
y decida cuándo usarlas.

    uv run python -m onco_research_ai.mcp_server.server      (transporte stdio)
"""

import logging
import sys

from mcp.server.mcpserver import MCPServer

from onco_research_ai.storage import queries

# En stdio, stdout es el canal del protocolo: los logs deben ir a stderr.
logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

mcp = MCPServer(
    name="oncoresearchai",
    instructions="Competitive intelligence on melanoma drugs (BRAF/MEK inhibitors and checkpoint "
    "inhibitors): clinical trials, scientific abstracts and FDA labels. Use query_trials and "
    "get_drug_profile for exact data, search_evidence for content, ask for a cited answer.",
)


@mcp.tool()
def search_evidence(
    query: str,
    k: int = 8,
    source: str | None = None,
    drug: str | None = None,
    phase: str | None = None,
) -> list[dict]:
    """Hybrid semantic + keyword search over trials, abstracts and FDA labels (English query).
    source: trial | publication | label | congress. drug: e.g. encorafenib. phase: e.g. PHASE3."""
    from onco_research_ai.agent.graph import get_retriever

    canonical = queries.resolve_drug(drug) if drug else None
    hits = get_retriever().search(
        query, k=min(k, 20), source=source, drugs=canonical, phases=phase
    )
    return [
        {
            k_: h.payload.get(k_)
            for k_ in ("source", "doc_id", "title", "year", "url", "text")
        }
        for h in hits
    ]


@mcp.tool()
def query_trials(
    drug: str | None = None,
    mechanism: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    sponsor_class: str | None = None,
    active_only: bool = False,
    limit: int = 20,
) -> list[dict]:
    """List melanoma clinical trials linked to the tracked drugs, with exact filters.
    mechanism: 'BRAF inhibitor' | 'MEK inhibitor' | 'anti-PD-1' | 'anti-CTLA-4' | 'anti-LAG-3'.
    phase: PHASE1..PHASE4. status: RECRUITING, COMPLETED... sponsor_class: INDUSTRY, NIH, OTHER."""
    return queries.list_trials(
        drug, mechanism, phase, status, sponsor_class, active_only, min(limit, 100)
    )


@mcp.tool()
def get_drug_profile(name: str) -> dict:
    """Profile of a drug (generic, brand or code name): mechanism, trials by phase and status,
    sponsors, key publications and FDA labels."""
    return queries.drug_profile(name) or {"error": f"unknown drug: {name}"}


@mcp.tool()
def get_landscape() -> dict:
    """Competitive landscape: trials per drug and phase, active trials, trials per start year,
    top industry sponsors."""
    return queries.landscape()


@mcp.tool()
def ask(question: str) -> dict:
    """Ask the OncoResearchAI agent; it answers with numbered citations to its sources."""
    from onco_research_ai.agent.graph import ask as agent_ask

    out = agent_ask(question)
    return {
        "answer": out["answer"],
        "sources": [
            {k: s[k] for k in ("ref", "title", "source", "url")}
            for s in out["cited_sources"]
        ],
        "sql": (out["sql"] or {}).get("sql"),
    }


if __name__ == "__main__":
    mcp.run("stdio")
