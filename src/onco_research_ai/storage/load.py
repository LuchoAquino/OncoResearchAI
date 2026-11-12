"""Carga los datos crudos validados en Postgres. Se puede repetir: vacía y recarga (idempotente)."""

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from onco_research_ai.ingestion.raw_store import latest_complete_run
from onco_research_ai.processing.drugs_seed import SEED
from onco_research_ai.processing.schemas import LabelIn, PublicationIn, TrialIn
from onco_research_ai.storage.db import get_engine, init_db
from onco_research_ai.storage.models import (
    Drug,
    DrugSynonym,
    Label,
    LabelDrug,
    LabelSection,
    Publication,
    PublicationDrug,
    Trial,
    TrialDrug,
    TrialIntervention,
    TrialPublication,
)

logger = logging.getLogger(__name__)
NCT_RE = re.compile(r"NCT\d{8}")


def _records(run_dir: Path, path: tuple[str, ...]) -> Iterator[dict]:
    for page_file in sorted(run_dir.glob("page_*.json")):
        page = json.loads(page_file.read_text(encoding="utf-8"))
        for key in path:
            page = page[key]
        yield from page


def _validated(items: Iterator[dict], model, name: str) -> list:
    """Valida cada registro; los inválidos se cuentan y se omiten (no tumban la carga)."""
    ok, bad = [], 0
    for raw in items:
        try:
            ok.append(model.from_raw(raw))
        except Exception as exc:  # noqa: BLE001
            bad += 1
            logger.warning(
                "%s inválido (%s): %r", name, exc.__class__.__name__, str(exc)[:120]
            )
    logger.info("%s: %d válidos, %d inválidos", name, len(ok), bad)
    return ok


def seed_drugs(session: Session) -> None:
    for name, syns in SEED.items():
        drug = Drug(canonical_name=name)
        drug.synonyms.append(DrugSynonym(synonym=name, kind="inn", source="manual"))
        for kind, values in syns.items():
            drug.synonyms += [
                DrugSynonym(synonym=v.lower(), kind=kind, source="manual")
                for v in values
            ]
        session.add(drug)
    session.flush()


def load_all() -> None:
    init_db()
    runs = {
        s: latest_complete_run(s) for s in ("clinicaltrials", "europepmc", "openfda")
    }
    if missing := [s for s, r in runs.items() if r is None]:
        raise SystemExit(f"Sin descarga completa de: {missing}")

    trials = _validated(
        _records(runs["clinicaltrials"], ("studies",)), TrialIn, "trials"
    )
    pubs = _validated(
        _records(runs["europepmc"], ("resultList", "result")), PublicationIn, "pubs"
    )
    labels = _validated(_records(runs["openfda"], ("results",)), LabelIn, "labels")
    # Europe PMC puede repetir un id entre páginas: nos quedamos con uno.
    pubs = list({p.id: p for p in pubs}.values())

    with Session(get_engine()) as s, s.begin():
        for table in (
            LabelDrug,
            PublicationDrug,
            TrialPublication,
            TrialDrug,
            TrialIntervention,
            Trial,
            Publication,
            LabelSection,
            Label,
            DrugSynonym,
            Drug,
        ):
            s.execute(delete(table))

        seed_drugs(s)
        for t in trials:
            row = Trial(
                **t.model_dump(exclude={"interventions", "reference_pmids"}),
                source_run=runs["clinicaltrials"].name,
            )
            row.interventions = [
                TrialIntervention(**i.model_dump()) for i in t.interventions
            ]
            s.add(row)
        for p in pubs:
            s.add(Publication(**p.model_dump(), source_run=runs["europepmc"].name))
        for lab in labels:
            row = Label(
                **lab.model_dump(exclude={"sections"}), source_run=runs["openfda"].name
            )
            row.sections = [
                LabelSection(name=k, text=v) for k, v in lab.sections.items()
            ]
            s.add(row)
        s.flush()
        link_trials_drugs(s)
        link_trials_publications(s, trials, pubs)
        link_publications_drugs(s, pubs)
        link_labels_drugs(s, labels)


def link_trials_drugs(s: Session) -> None:
    """Un ensayo prueba un fármaco si algún sinónimo aparece como palabra en sus intervenciones."""
    syns = s.execute(select(DrugSynonym.synonym, DrugSynonym.drug_id)).all()
    patterns = [
        (re.compile(rf"(?<![\w-]){re.escape(sy)}(?![\w-])", re.IGNORECASE), sy, d)
        for sy, d in syns
    ]
    n = 0
    for nct, name, others in s.execute(
        select(
            TrialIntervention.nct_id,
            TrialIntervention.name,
            TrialIntervention.other_names,
        )
    ):
        text = " | ".join([name, *others])
        for pat, sy, drug_id in patterns:
            if pat.search(text) and not s.get(TrialDrug, (nct, drug_id)):
                s.add(TrialDrug(nct_id=nct, drug_id=drug_id, matched_text=sy))
                n += 1
        s.flush()
    logger.info("trial_drugs: %d vínculos", n)


def link_trials_publications(
    s: Session, trials: list[TrialIn], pubs: list[PublicationIn]
) -> None:
    by_pmid = {p.pmid: p.id for p in pubs if p.pmid}
    nct_ids = {t.nct_id for t in trials}
    links: set[tuple[str, str, str]] = set()
    for t in trials:  # ruta 1: el ensayo lista el artículo en sus referencias
        for pmid in t.reference_pmids:
            if pmid in by_pmid:
                links.add((t.nct_id, by_pmid[pmid], "trial_reference"))
    for p in pubs:  # ruta 2: el artículo cita el NCT
        for nct in set(NCT_RE.findall(f"{p.title} {p.abstract or ''}")) & nct_ids:
            links.add((nct, p.id, "abstract_mention"))
    s.add_all(
        TrialPublication(nct_id=a, publication_id=b, link_type=c) for a, b, c in links
    )
    logger.info("trial_publications: %d vínculos", len(links))


def _drug_patterns(s: Session) -> list[tuple[re.Pattern, str, int]]:
    """Un patrón por sinónimo: coincide solo con la palabra completa (sin importar mayúsculas)."""
    syns = s.execute(select(DrugSynonym.synonym, DrugSynonym.drug_id)).all()
    return [
        (re.compile(rf"(?<![\w-]){re.escape(sy)}(?![\w-])", re.IGNORECASE), sy, d)
        for sy, d in syns
    ]


def link_publications_drugs(s: Session, pubs: list[PublicationIn]) -> None:
    """Un artículo se enlaza a un fármaco si algún sinónimo aparece en su título o abstract."""
    patterns = _drug_patterns(s)
    rows = {}
    for p in pubs:
        for pat, sy, drug_id in patterns:
            if (key := (p.id, drug_id)) not in rows:
                in_title = bool(pat.search(p.title))
                if in_title or (p.abstract and pat.search(p.abstract)):
                    rows[key] = PublicationDrug(
                        publication_id=p.id,
                        drug_id=drug_id,
                        matched_text=sy,
                        in_title=in_title,
                    )
    s.add_all(rows.values())
    logger.info("publication_drugs: %d vínculos", len(rows))


def link_labels_drugs(s: Session, labels: list[LabelIn]) -> None:
    """Ficha -> fármaco por el nombre del bloque openfda; si falta, por el texto de la ficha."""
    patterns = _drug_patterns(s)
    n = 0
    for lab in labels:
        names = " | ".join(x for x in (lab.generic_name, lab.brand_name) if x)
        source, text = (
            ("openfda_name", names)
            if names
            else (
                "text",
                lab.sections.get("indications_and_usage", "")[:300],
            )
        )
        seen = set()
        for pat, sy, drug_id in patterns:
            if drug_id not in seen and pat.search(text):
                seen.add(drug_id)
                s.add(
                    LabelDrug(
                        set_id=lab.set_id,
                        drug_id=drug_id,
                        matched_text=sy,
                        match_source=source,
                    )
                )
                n += 1
    logger.info("label_drugs: %d vínculos", n)


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    load_all()
