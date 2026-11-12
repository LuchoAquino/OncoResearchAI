"""Controles de calidad de datos. Cada control es una consulta SQL con nombre y explicación.

Dos clases:
- "error": cuenta filas IMPOSIBLES o duplicadas; el valor esperado es 0.
- "rate": mide un porcentaje informativo (completitud, alineación); no falla, se reporta.
"""

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import text

from onco_research_ai.storage.db import get_engine

logger = logging.getLogger(__name__)


@dataclass
class Check:
    group: str
    name: str
    what: str  # qué mide, en cristiano
    kind: str  # "error" | "rate"
    sql: str  # error: devuelve 1 número (filas malas). rate: devuelve (parte, total)


CHECKS = [
    # ---------------------------------------------------------------- completitud
    Check(
        "Completitud",
        "Ensayos sin resumen",
        "trials.brief_summary vacío",
        "rate",
        "select count(*) filter (where brief_summary is null), count(*) from trials",
    ),
    Check(
        "Completitud",
        "Ensayos sin fecha de inicio",
        "trials.start_date vacío",
        "rate",
        "select count(*) filter (where start_date is null), count(*) from trials",
    ),
    Check(
        "Completitud",
        "Ensayos sin tamaño (enrollment)",
        "trials.enrollment vacío",
        "rate",
        "select count(*) filter (where enrollment is null), count(*) from trials",
    ),
    Check(
        "Completitud",
        "Ensayos sin patrocinador",
        "trials.sponsor_name vacío",
        "rate",
        "select count(*) filter (where sponsor_name is null), count(*) from trials",
    ),
    Check(
        "Completitud",
        "Artículos sin abstract",
        "publications.abstract vacío",
        "rate",
        "select count(*) filter (where abstract is null), count(*) from publications",
    ),
    Check(
        "Completitud",
        "Artículos sin PMID",
        "publications.pmid vacío (preprints)",
        "rate",
        "select count(*) filter (where pmid is null), count(*) from publications",
    ),
    Check(
        "Completitud",
        "Artículos sin DOI",
        "publications.doi vacío",
        "rate",
        "select count(*) filter (where doi is null), count(*) from publications",
    ),
    Check(
        "Completitud",
        "Fichas sin nombre de marca",
        "labels.brand_name vacío (sin bloque openfda)",
        "rate",
        "select count(*) filter (where brand_name is null), count(*) from labels",
    ),
    # ---------------------------------------------------------------- consistencia
    Check(
        "Consistencia",
        "Ensayos que terminan antes de empezar",
        "completion_date < start_date",
        "error",
        "select count(*) from trials where completion_date < start_date",
    ),
    Check(
        "Consistencia",
        "Ensayos con tamaño <= 0",
        "enrollment <= 0 salvo WITHDRAWN (cancelados antes de reclutar: 0 es correcto)",
        "error",
        "select count(*) from trials where enrollment <= 0 and overall_status <> 'WITHDRAWN'",
    ),
    Check(
        "Consistencia",
        "Artículos con año futuro",
        "pub_year > año actual",
        "error",
        f"select count(*) from publications where pub_year > {date.today().year}",
    ),
    Check(
        "Consistencia",
        "Estudios intervencionales sin fase",
        "INTERVENTIONAL con phases vacío (debería ser NA)",
        "error",
        "select count(*) from trials where study_type = 'INTERVENTIONAL' and cardinality(phases) = 0",
    ),
    # ---------------------------------------------------------------- duplicados
    Check(
        "Duplicados",
        "DOI repetido en artículos",
        "mismo DOI en más de una fila",
        "error",
        "select count(*) from (select doi from publications where doi is not null group by doi having count(*) > 1) t",
    ),
    Check(
        "Duplicados",
        "Título+año repetido en artículos",
        "mismo título y año en más de una fila",
        "error",
        "select count(*) from (select lower(title), pub_year from publications group by 1, 2 having count(*) > 1) t",
    ),
    # ---------------------------------------------------------------- pertinencia
    Check(
        "Pertinencia",
        "Ensayos que NO son de melanoma",
        "conditions no nombra melanoma (suelen ser ensayos genéricos: «Solid Tumors», «Skin Cancer»)",
        "rate",
        "select count(*) filter (where not exists (select 1 from unnest(conditions) c where c ilike '%melanoma%')), count(*) from trials",
    ),
    Check(
        "Pertinencia",
        "Artículos uveales o de otra zona",
        "título o abstract mencionan 'uveal'",
        "rate",
        "select count(*) filter (where title ilike '%uveal%' or abstract ilike '%uveal%'), count(*) from publications",
    ),
    # ---------------------------------------------------------------- alineación
    Check(
        "Alineación",
        "Ensayos con fármaco identificado",
        "aparecen en trial_drugs",
        "rate",
        "select count(distinct nct_id), (select count(*) from trials) from trial_drugs",
    ),
    Check(
        "Alineación",
        "Artículos con fármaco identificado",
        "aparecen en publication_drugs",
        "rate",
        "select count(distinct publication_id), (select count(*) from publications) from publication_drugs",
    ),
    Check(
        "Alineación",
        "Fichas con fármaco identificado",
        "aparecen en label_drugs",
        "rate",
        "select count(distinct set_id), (select count(*) from labels) from label_drugs",
    ),
    Check(
        "Alineación",
        "Ensayos enlazados a algún artículo",
        "aparecen en trial_publications",
        "rate",
        "select count(distinct nct_id), (select count(*) from trials) from trial_publications",
    ),
    Check(
        "Alineación",
        "Ensayos con fármaco Y artículo",
        "aparecen en ambas tablas de cruce",
        "rate",
        "select count(*), (select count(*) from trials) from trials t where exists (select 1 from trial_drugs d where d.nct_id=t.nct_id) and exists (select 1 from trial_publications p where p.nct_id=t.nct_id)",
    ),
    # ---------------------------------------------------------------- extractor LLM
    Check(
        "Extractor LLM",
        "Extracciones con alguna cifra no verificada",
        "unverified_fields no vacío",
        "rate",
        "select count(*) filter (where cardinality(unverified_fields) > 0), count(*) from publication_extractions",
    ),
]


def run_checks() -> list[dict]:
    results = []
    with get_engine().connect() as conn:
        for c in CHECKS:
            row = conn.execute(text(c.sql)).one()
            if c.kind == "error":
                results.append({"check": c, "bad": row[0], "ok": row[0] == 0})
            else:
                part, total = row
                results.append(
                    {
                        "check": c,
                        "part": part,
                        "total": total,
                        "pct": 100 * part / total if total else 0.0,
                    }
                )
    return results


def render_markdown(results: list[dict]) -> str:
    lines = [f"# Informe de calidad de datos — {date.today()}", ""]
    group = None
    for r in results:
        c = r["check"]
        if c.group != group:
            group = c.group
            lines += [
                "",
                f"## {group}",
                "",
                "| Control | Qué mide | Resultado |",
                "|---|---|---|",
            ]
        res = (
            ("✔ 0" if r["ok"] else f"✘ {r['bad']}")
            if c.kind == "error"
            else f"{r['pct']:.1f} % ({r['part']} de {r['total']})"
        )
        lines.append(f"| {c.name} | {c.what} | {res} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    from onco_research_ai.logging_config import setup_logging

    setup_logging()
    report = render_markdown(run_checks())
    out = Path("eval/reports") / f"quality_{date.today()}.md"
    out.write_text(report, encoding="utf-8")
    print(report)
    logger.info("Informe guardado en %s", out)
