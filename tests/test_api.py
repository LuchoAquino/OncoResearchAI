"""Tests de la API y del servidor MCP contra la base de datos real (se saltan si no está)."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from onco_research_ai.storage import queries

try:
    queries.health()
    DB_UP = True
except Exception:  # noqa: BLE001
    DB_UP = False

pytestmark = pytest.mark.skipif(not DB_UP, reason="Postgres no disponible")


@pytest.fixture(scope="module")
def client():
    from onco_research_ai.api.main import app

    return TestClient(app)


def test_health(client):
    r = client.get("/health").json()
    assert r["postgres"]["trials"] > 0
    assert "chunks_minilm" in r["qdrant"]


def test_trials_filters_and_shows_all_drugs_of_each_trial(client):
    rows = client.get("/trials", params={"drug": "braftovi", "phase": "PHASE3"}).json()
    columbus = next(r for r in rows if r["nct_id"] == "NCT01909453")  # COLUMBUS
    assert {"encorafenib", "binimetinib"} <= set(columbus["drugs"])
    assert all("PHASE3" in r["phases"] for r in rows)


def test_drug_profile_resolves_brand_and_code_names(client):
    assert client.get("/drugs/Keytruda").json()["name"] == "pembrolizumab"
    assert client.get("/drugs/MK-3475").json()["mechanism"] == "anti-PD-1"
    assert client.get("/drugs/aspirin").status_code == 404


def test_landscape_has_every_drug(client):
    active = client.get("/landscape").json()["active_by_drug"]
    assert len(active) == 10


def test_mcp_server_lists_tools():
    from onco_research_ai.mcp_server.server import mcp

    tools = asyncio.run(mcp.list_tools())
    assert {t.name for t in tools} == {
        "search_evidence",
        "query_trials",
        "get_drug_profile",
        "get_landscape",
        "ask",
    }
