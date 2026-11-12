"""Tests de la ingestión con un servidor HTTP FALSO: sin red, rápidos y deterministas."""

import json

import httpx
import pytest
from tenacity import wait_none

from onco_research_ai.ingestion import chembl, clinicaltrials, europepmc, openfda
from onco_research_ai.ingestion.http import get_json, make_client
from onco_research_ai.ingestion.raw_store import (
    latest_complete_run,
    read_manifest,
    save_run,
)


@pytest.fixture(autouse=True)
def no_waiting(monkeypatch):
    """Los reintentos esperan 1 s, 2 s, 4 s...; en los tests no queremos esperar."""
    monkeypatch.setattr(get_json.retry, "wait", wait_none())


def client_for(handler) -> httpx.Client:
    return make_client(transport=httpx.MockTransport(handler))


# ---------- reintentos ----------


def test_retries_transient_errors_then_succeeds():
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(500)
        return httpx.Response(200, json={"ok": True})

    with client_for(handler) as client:
        assert get_json(client, "https://x.test/a") == {"ok": True}
    assert len(calls) == 3  # 2 fallos + 1 éxito


def test_does_not_retry_client_errors():
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(404)

    with client_for(handler) as client, pytest.raises(httpx.HTTPStatusError):
        get_json(client, "https://x.test/a")
    assert len(calls) == 1  # un 404 no se arregla reintentando


# ---------- paginación ----------


def test_clinicaltrials_follows_page_tokens_until_none():
    pages = {
        None: {"studies": [{"n": 1}], "nextPageToken": "t1"},
        "t1": {"studies": [{"n": 2}], "nextPageToken": "t2"},
        "t2": {"studies": [{"n": 3}]},  # sin token = última página
    }

    def handler(request):
        return httpx.Response(200, json=pages[request.url.params.get("pageToken")])

    with client_for(handler) as client:
        assert len(list(clinicaltrials.iter_pages(client))) == 3
        assert len(list(clinicaltrials.iter_pages(client, max_pages=2))) == 2


def test_europepmc_stops_when_cursor_does_not_advance():
    pages = {
        "*": {"resultList": {"result": [{"id": 1}]}, "nextCursorMark": "A"},
        "A": {
            "resultList": {"result": [{"id": 2}]},
            "nextCursorMark": "A",
        },  # mismo cursor
    }

    def handler(request):
        return httpx.Response(200, json=pages[request.url.params["cursorMark"]])

    with client_for(handler) as client:
        assert len(list(europepmc.iter_pages(client))) == 2


def test_openfda_pages_by_skip_until_total(monkeypatch):
    monkeypatch.setattr(openfda, "PAGE_SIZE", 2)
    skips = []

    def handler(request):
        skips.append(int(request.url.params["skip"]))
        return httpx.Response(
            200, json={"meta": {"results": {"total": 5}}, "results": [{}]}
        )

    with client_for(handler) as client:
        assert len(list(openfda.iter_pages(client))) == 3
    assert skips == [0, 2, 4]


def test_chembl_keeps_going_when_one_drug_fails(monkeypatch):
    monkeypatch.setattr(chembl, "DRUGS", ["bad", "good"])

    def handler(request):
        params = request.url.params
        if request.url.path.endswith("molecule/search.json"):
            if params["q"] == "bad":
                return httpx.Response(500)  # falla siempre, se agotan los reintentos
            return httpx.Response(
                200,
                json={
                    "molecules": [
                        {"molecule_chembl_id": "CHEMBL1", "pref_name": "good"}
                    ]
                },
            )
        return httpx.Response(200, json={"mechanisms": []})

    with client_for(handler) as client:
        pages = list(chembl.iter_pages(client))
    assert "error" in pages[0] and pages[0]["drug_query"] == "bad"
    assert pages[1]["molecule"]["molecule_chembl_id"] == "CHEMBL1"
    assert sum(chembl.count_records(p) for p in pages) == 1


# ---------- guardado crudo ----------


def test_save_run_writes_pages_and_manifest_last(tmp_path):
    pages = [{"studies": [1, 2]}, {"studies": [3]}]
    run_dir = save_run(
        source="demo",
        query={"q": "melanoma"},
        pages=pages,
        count_records=lambda p: len(p["studies"]),
        root=tmp_path,
    )
    assert json.loads((run_dir / "page_0001.json").read_text()) == pages[0]
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["n_pages"] == 2
    assert manifest["n_records"] == 3
    assert manifest["query"] == {"q": "melanoma"}


def test_run_with_errors_is_partial_and_not_picked_as_latest(tmp_path):
    ok_pages = [{"n": 1}]
    count = lambda p: 0 if "error" in p else 1
    is_err = lambda p: "error" in p

    good = save_run("demo", {}, ok_pages, count, is_error=is_err, root=tmp_path)
    assert read_manifest(good)["status"] == "complete"

    # una descarga POSTERIOR que falló del todo: tiene manifest, pero es parcial
    (tmp_path / "demo" / "99999999T999999Z").mkdir()
    bad = tmp_path / "demo" / "99999999T999999Z"
    (bad / "manifest.json").write_text('{"status": "partial"}')
    # y otra aún más reciente, cortada a medias: ni siquiera tiene manifest
    (tmp_path / "demo" / "99999999T999999Zz").mkdir()

    assert latest_complete_run("demo", root=tmp_path) == good


def test_all_errors_run_is_partial(tmp_path):
    run = save_run(
        "demo",
        {},
        [{"error": "x"}, {"error": "y"}],
        count_records=lambda p: 0,
        is_error=lambda p: True,
        root=tmp_path,
    )
    manifest = read_manifest(run)
    assert manifest["status"] == "partial"
    assert manifest["n_errors"] == 2
    assert latest_complete_run("demo", root=tmp_path) is None


def test_parse_partial_date():
    from datetime import date

    from onco_research_ai.processing.schemas import parse_partial_date

    assert parse_partial_date("2024-05") == date(2024, 5, 1)
    assert parse_partial_date("2024-05-31") == date(2024, 5, 31)
    assert parse_partial_date("20260507") == date(2026, 5, 7)
    assert parse_partial_date(None) is None


def test_synonym_pattern_matches_hyphenated_but_not_inside_words():
    import re

    pat = re.compile(r"(?<!\w)nivolumab(?!\w)", re.IGNORECASE)
    assert pat.search("vemurafenib-resistant melanoma and nivolumab-treated")
    assert pat.search("Nivolumab, ipilimumab")
    assert not pat.search("prenivolumabx")


def test_unverified_fields_flags_numbers_not_in_abstract():
    from onco_research_ai.processing.extractor import Extraction, unverified_fields

    abstract = (
        "n = 314, n = 316 and n = 315 patients. Median OS was 72.1 months. ORR 46,5%."
    )
    ext = Extraction(
        study_kind="randomized_trial",
        treatment_line="first_line",
        n_patients=945,
        os_months=72.1,
        orr_percent=46.5,
    )
    assert unverified_fields(ext, abstract) == [
        "n_patients"
    ]  # 945 es la suma, no está escrito


def test_dedupe_publications_keeps_published_over_preprint():
    from onco_research_ai.processing.schemas import PublicationIn
    from onco_research_ai.storage.load import dedupe_publications

    def pub(id_, source, doi, title="Same Paper"):
        return PublicationIn(id=id_, source=source, doi=doi, title=title, pub_year=2022)

    out = dedupe_publications(
        [
            pub("PPR:1", "PPR", "10.1/x"),
            pub("MED:1", "MED", "10.1/x"),
            pub("MED:2", "MED", None, "Other"),
        ]
    )
    assert sorted(p.id for p in out) == ["MED:1", "MED:2"]


def test_split_text_respects_limit_and_overlaps_one_sentence():
    from onco_research_ai.processing.chunking import split_text

    count = lambda s: len(s.split())
    text = "Aaa bbb ccc. Ddd eee fff. Ggg hhh iii. Jjj kkk lll."
    chunks = split_text(text, count, max_tokens=7, overlap=1)
    assert chunks == [
        "Aaa bbb ccc. Ddd eee fff.",
        "Ddd eee fff. Ggg hhh iii.",
        "Ggg hhh iii. Jjj kkk lll.",
    ]
    assert all(count(c) <= 7 for c in chunks)


def test_chunk_point_id_is_deterministic():
    from onco_research_ai.processing.chunking import Chunk

    assert Chunk("NCT1", 0, "x").point_id == Chunk("NCT1", 0, "otro texto").point_id
    assert Chunk("NCT1", 0, "x").point_id != Chunk("NCT1", 1, "x").point_id


def test_bm25_tokenize_keeps_codes_and_their_parts():
    from onco_research_ai.retrieval.bm25 import tokenize

    assert tokenize("MK-3475 (pembrolizumab) in the patients") == [
        "mk-3475",
        "mk",
        "3475",
        "pembrolizumab",
    ]


def test_bm25_filters_behave_like_qdrant():
    from onco_research_ai.retrieval.bm25 import matches

    payload = {
        "source": "trial",
        "drugs": ["nivolumab", "relatlimab"],
        "phases": ["PHASE3"],
    }
    assert matches(
        payload, {"source": "trial", "drugs": "relatlimab", "phases": "PHASE3"}
    )
    assert not matches(payload, {"drugs": "ipilimumab"})
    assert matches(payload, {"drugs": None})  # filtro vacío = sin filtrar


def test_best_per_doc_keeps_first_chunk_of_each_document():
    from onco_research_ai.retrieval.hybrid import Hit, best_per_doc

    hits = [
        Hit("1", {"doc_id": "A"}, 3),
        Hit("2", {"doc_id": "A"}, 2),
        Hit("3", {"doc_id": "B"}, 1),
    ]
    assert [h.point_id for h in best_per_doc(hits)] == ["1", "3"]
