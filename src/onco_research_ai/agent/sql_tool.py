"""Pregunta en lenguaje natural -> SQL -> filas. Con varias capas de seguridad.

Un LLM que escribe SQL es peligroso si nadie lo vigila (podría borrar tablas o colgar la base):
1. sqlglot analiza el SQL: una sola sentencia, solo SELECT, solo tablas conocidas.
2. Se ejecuta en una transacción de SOLO LECTURA: Postgres rechaza cualquier escritura.
3. Tiempo máximo de 5 s y como mucho 50 filas.
Si falla, se le devuelve el error al LLM una vez para que lo corrija.
"""

import logging
from dataclasses import dataclass, field

import sqlglot
from pydantic import BaseModel
from sqlalchemy import text
from sqlglot import exp

from onco_research_ai.llm.client import complete_json
from onco_research_ai.storage.db import get_engine

logger = logging.getLogger(__name__)
MAX_ROWS = 50

SCHEMA = """PostgreSQL database about melanoma competitive intelligence.

trials(nct_id PK, brief_title, official_title, brief_summary, study_type, overall_status,
       phases text[], conditions text[], sponsor_name, sponsor_class, start_date date,
       completion_date date, enrollment int, has_results bool)
  study_type: INTERVENTIONAL | OBSERVATIONAL | EXPANDED_ACCESS
  overall_status: RECRUITING | NOT_YET_RECRUITING | ACTIVE_NOT_RECRUITING | ENROLLING_BY_INVITATION
                  | COMPLETED | TERMINATED | WITHDRAWN | SUSPENDED | UNKNOWN | AVAILABLE | NO_LONGER_AVAILABLE
  phases values: EARLY_PHASE1, PHASE1, PHASE2, PHASE3, PHASE4, NA. Filter with 'PHASE3' = ANY(phases).
  sponsor_class: INDUSTRY | NIH | OTHER | OTHER_GOV | NETWORK | FED | INDIV
trial_interventions(id, nct_id FK, name, type, other_names text[])
drugs(id PK, canonical_name lowercase INN, mechanism)
  canonical_name: encorafenib, binimetinib, dabrafenib, trametinib, vemurafenib, cobimetinib,
                  pembrolizumab, nivolumab, ipilimumab, relatlimab
  mechanism: 'BRAF inhibitor' | 'MEK inhibitor' | 'anti-PD-1' | 'anti-CTLA-4' | 'anti-LAG-3'
drug_synonyms(drug_id FK, synonym lowercase, kind inn|brand|code)  -- e.g. keytruda, mk-3475
trial_drugs(nct_id FK, drug_id FK, matched_text)          -- which trial tests which drug
publications(id PK, source, pmid, doi, title, abstract, journal, pub_year int, pub_types text[],
             is_open_access bool, cited_by_count int)
publication_drugs(publication_id FK, drug_id FK, matched_text, in_title bool)
  in_title = true means the article is ABOUT the drug (prefer it).
trial_publications(nct_id FK, publication_id FK, link_type)   -- trial_reference | abstract_mention
labels(set_id PK, version, effective_date, generic_name, brand_name, manufacturer)  -- FDA labels
label_drugs(set_id FK, drug_id FK, matched_text, match_source)
label_sections(set_id FK, name, text)
publication_extractions(publication_id, study_kind, treatment_line, n_patients, orr_percent,
                        pfs_months, os_months, unverified_fields text[])  -- LLM-extracted, only ~50 rows

Notes: count trials with COUNT(DISTINCT nct_id) when joining. Drug names are lowercase.
Only the 10 drugs above are linked; other drugs only appear in free text (ILIKE).

Drug classes (ALWAYS filter by d.mechanism; never list drug names by hand unless the user names
specific drugs):
  "BRAF inhibitors"  = d.mechanism = 'BRAF inhibitor'  (encorafenib, dabrafenib, vemurafenib)
  "MEK inhibitors"   = d.mechanism = 'MEK inhibitor'   (binimetinib, trametinib, cobimetinib)
  "targeted therapy" = BRAF inhibitor OR MEK inhibitor
  "immunotherapy" / "checkpoint inhibitors" = d.mechanism LIKE 'anti-%'
BRAF and MEK inhibitors are DIFFERENT classes: a question about BRAF inhibitors must not
include binimetinib, trametinib or cobimetinib.
"""
ALLOWED_TABLES = {
    "trials",
    "trial_interventions",
    "drugs",
    "drug_synonyms",
    "trial_drugs",
    "publications",
    "publication_drugs",
    "trial_publications",
    "labels",
    "label_drugs",
    "label_sections",
    "publication_extractions",
}


class SQLDraft(BaseModel):
    sql: str
    explanation: str


@dataclass
class SQLResult:
    sql: str = ""
    explanation: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    error: str | None = None

    def as_text(self) -> str:
        if self.error:
            return f"SQL error: {self.error}"
        head = " | ".join(self.columns)
        body = "\n".join(" | ".join(str(v) for v in r) for r in self.rows)
        return f"Query: {self.sql}\n{head}\n{body or '(no rows)'}"


class UnsafeSQL(ValueError):
    pass


def validate(sql: str) -> str:
    """Devuelve el SQL normalizado (con LIMIT) o lanza UnsafeSQL."""
    statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Select | exp.Union):
        raise UnsafeSQL("only SELECT queries are allowed")
    if any(
        isinstance(n, exp.Insert | exp.Update | exp.Delete | exp.Drop | exp.Create)
        for n in tree.walk()
    ):
        raise UnsafeSQL("write operations are not allowed")
    ctes = {c.alias_or_name for c in tree.find_all(exp.CTE)}
    tables = {t.name for t in tree.find_all(exp.Table)} - ctes
    if unknown := tables - ALLOWED_TABLES:
        raise UnsafeSQL(f"unknown tables: {sorted(unknown)}")
    if isinstance(tree, exp.Select) and not tree.args.get("limit"):
        tree = tree.limit(MAX_ROWS)
    return tree.sql(dialect="postgres")


def execute(sql: str) -> tuple[list[str], list[list]]:
    with get_engine().connect() as conn, conn.begin():
        conn.execute(text("SET TRANSACTION READ ONLY"))
        conn.execute(text("SET LOCAL statement_timeout = 5000"))
        res = conn.execute(text(sql))
        rows = [list(r) for r in res.fetchmany(MAX_ROWS)]
        return list(res.keys()), [[_jsonable(v) for v in r] for r in rows]


def _jsonable(v):
    return v if isinstance(v, int | float | str | bool | type(None)) else str(v)


def run_sql_tool(question: str) -> SQLResult:
    messages = [
        {
            "role": "system",
            "content": "You write one PostgreSQL SELECT query to answer the user "
            'question with this schema. Reply JSON {"sql": str, "explanation": str}.\n\n'
            + SCHEMA,
        },
        {"role": "user", "content": question},
    ]
    result = SQLResult()
    for attempt in range(2):
        try:
            draft = complete_json(messages, SQLDraft)
            result.sql, result.explanation = validate(draft.sql), draft.explanation
            result.columns, result.rows = execute(result.sql)
            result.error = None
            if result.rows or attempt == 1:
                return result
            # 0 filas: puede ser verdad o un SQL mal planteado (p. ej. exigir dos condiciones
            # excluyentes en la MISMA fila). Un "no existe" falso es el peor error para un
            # analista, así que se pide una revisión antes de aceptarlo.
            messages += [
                {"role": "assistant", "content": result.sql},
                {
                    "role": "user",
                    "content": "The query returned 0 rows. Check the logic (e.g. "
                    "conditions on different joined rows, wrong values, too strict filters). If it "
                    "is correct, return the same query; otherwise fix it.",
                },
            ]
            continue
        except Exception as exc:  # noqa: BLE001
            result.error = f"{exc.__class__.__name__}: {str(exc)[:300]}"
            logger.warning("SQL intento %d falló: %s", attempt + 1, result.error)
            messages += [
                {"role": "assistant", "content": result.sql or "(invalid)"},
                {
                    "role": "user",
                    "content": f"That failed with: {result.error}. Fix it.",
                },
            ]
    return result
