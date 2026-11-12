"""Extractor con LLM: del abstract de un artículo a un formulario fijo (Pydantic) y verificado.

Anti-alucinación en tres capas:
1. El prompt exige `null` cuando el dato no está en el texto.
2. Pydantic rechaza valores fuera del formulario (p. ej. una línea de tratamiento inventada).
3. Cada cifra devuelta debe aparecer literalmente en el abstract; si no, se marca `unverified`.
"""

import argparse
import json
import logging
import re
import time
from typing import Literal

import litellm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from onco_research_ai.config import settings
from onco_research_ai.storage.db import get_engine, init_db
from onco_research_ai.storage.models import Publication, PublicationExtraction

logger = logging.getLogger(__name__)
MODEL = "groq/openai/gpt-oss-120b"
NUMERIC_FIELDS = ["n_patients", "orr_percent", "pfs_months", "os_months"]


class Extraction(BaseModel):
    study_kind: Literal[
        "randomized_trial",
        "single_arm_trial",
        "observational",
        "case_report",
        "review_or_meta_analysis",
        "preclinical",
        "other",
    ]
    treatment_line: Literal[
        "first_line", "later_line", "adjuvant", "neoadjuvant", "mixed", "not_stated"
    ]
    n_patients: int | None = None
    orr_percent: float | None = None
    pfs_months: float | None = None
    os_months: float | None = None


SYSTEM_PROMPT = f"""You extract structured data from a melanoma paper abstract.
Reply with ONE JSON object and nothing else, matching this JSON schema:
{json.dumps(Extraction.model_json_schema()["properties"], indent=1)}

Rules:
- Use ONLY information stated in the abstract. If a value is not stated, use null. Never estimate.
- n_patients: total number of patients analysed in the study (not a subgroup).
- orr_percent: overall objective response rate as a percentage, for the main/experimental group.
- pfs_months / os_months: MEDIAN progression-free / overall survival in months, main group.
  If given in other units (weeks, years) or only as a rate (e.g. "2-year OS 60%"), use null.
- treatment_line: "not_stated" if the abstract does not say."""


def numbers_in(text: str) -> set[str]:
    """Todos los números del texto, normalizados: '14,9' y '14.9' -> '14.9'; '1,234' -> '1234'."""
    found = set()
    for tok in re.findall(r"\d+(?:[.,]\d+)*", text):
        found.add(tok.replace(",", "").rstrip("."))  # 1,234 -> 1234
        found.add(tok.replace(",", "."))  # 14,9 -> 14.9
    return found


def unverified_fields(ext: Extraction, abstract: str) -> list[str]:
    present = numbers_in(abstract)
    bad = []
    for name in NUMERIC_FIELDS:
        value = getattr(ext, name)
        if value is not None and f"{value:g}" not in present:
            bad.append(name)
    return bad


def extract(abstract: str) -> Extraction:
    resp = litellm.completion(
        model=MODEL,
        api_key=settings.groq_api_key,
        temperature=0,
        response_format={"type": "json_object"},
        num_retries=5,
        reasoning_effort="low",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": abstract},
        ],
    )
    return Extraction.model_validate_json(resp.choices[0].message.content)


def run(limit: int, pause: float = 4.0) -> None:
    init_db()
    with Session(get_engine()) as s:
        done = select(PublicationExtraction.publication_id)
        pubs = s.scalars(
            select(Publication)
            .where(Publication.abstract.is_not(None), Publication.id.not_in(done))
            .where(Publication.pub_year >= 2020)
            .order_by(Publication.cited_by_count.desc().nulls_last())
            .limit(limit)
        ).all()
        for i, pub in enumerate(pubs, 1):
            try:
                ext = extract(pub.abstract)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "%s: fallo (%s) %s", pub.id, exc.__class__.__name__, str(exc)[:120]
                )
                continue
            bad = unverified_fields(ext, pub.abstract)
            s.add(
                PublicationExtraction(
                    publication_id=pub.id,
                    model=MODEL,
                    unverified_fields=bad,
                    raw_output=ext.model_dump(),
                    **ext.model_dump(),
                )
            )
            s.commit()
            logger.info(
                "[%d/%d] %s %s%s",
                i,
                len(pubs),
                pub.id,
                ext.model_dump(),
                f" NO VERIFICADO: {bad}" if bad else "",
            )
            time.sleep(pause)  # cuota gratuita de Groq: pocas peticiones por minuto


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=10)
    setup_logging()
    run(ap.parse_args().limit)
