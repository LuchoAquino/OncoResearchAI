"""Consultas SQL fijas (no generadas por el LLM) que comparten la API, el servidor MCP y la UI.

Usan parámetros (:drug, :phase...) en vez de pegar texto en el SQL: así un valor malicioso
nunca puede convertirse en código (inyección SQL).
"""

from sqlalchemy import bindparam, text

from onco_research_ai.storage.db import get_engine

ACTIVE_STATUSES = (
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "ENROLLING_BY_INVITATION",
)


def _rows(sql: str, **params) -> list[dict]:
    with get_engine().connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def resolve_drug(name: str) -> str | None:
    """'Keytruda', 'MK-3475' o 'pembrolizumab' -> 'pembrolizumab'."""
    rows = _rows(
        "select d.canonical_name from drugs d join drug_synonyms s on s.drug_id = d.id "
        "where s.synonym = lower(:n) limit 1",
        n=name.strip(),
    )
    return rows[0]["canonical_name"] if rows else None


def list_drugs() -> list[dict]:
    return _rows(
        "select d.canonical_name as name, d.mechanism, "
        "array_agg(s.synonym order by s.kind) filter (where s.kind <> 'inn') as synonyms "
        "from drugs d join drug_synonyms s on s.drug_id = d.id group by 1, 2 order by 2, 1"
    )


def list_trials(
    drug: str | None = None,
    mechanism: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    sponsor_class: str | None = None,
    active_only: bool = False,
    limit: int = 50,
) -> list[dict]:
    if drug:
        drug = resolve_drug(drug) or drug.lower()
    sql = """
        select t.nct_id, t.brief_title, t.phases, t.overall_status, t.sponsor_name,
               t.sponsor_class, t.start_date, t.enrollment,
               (select array_agg(distinct d2.canonical_name) from trial_drugs td2
                  join drugs d2 on d2.id = td2.drug_id where td2.nct_id = t.nct_id) as drugs,
               'https://clinicaltrials.gov/study/' || t.nct_id as url
        from trials t
        where exists (
                select 1 from trial_drugs td join drugs d on d.id = td.drug_id
                where td.nct_id = t.nct_id
                  and (cast(:drug as text) is null or d.canonical_name = :drug)
                  and (cast(:mechanism as text) is null or d.mechanism = :mechanism))
          and (cast(:phase as text) is null or :phase = any(t.phases))
          and (cast(:status as text) is null or t.overall_status = :status)
          and (cast(:sponsor_class as text) is null or t.sponsor_class = :sponsor_class)
          and (not :active_only or t.overall_status in :active)
        order by t.start_date desc nulls last
        limit :limit
    """
    with get_engine().connect() as conn:
        stmt = text(sql).bindparams(bindparam("active", expanding=True))
        res = conn.execute(
            stmt,
            {
                "drug": drug,
                "mechanism": mechanism,
                "phase": phase,
                "status": status,
                "sponsor_class": sponsor_class,
                "active_only": active_only,
                "active": list(ACTIVE_STATUSES),
                "limit": min(limit, 500),
            },
        )
        return [_clean(dict(r._mapping)) for r in res]


def _clean(row: dict) -> dict:
    return {
        k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in row.items()
    }


def drug_profile(name: str) -> dict | None:
    canonical = resolve_drug(name)
    if not canonical:
        return None
    p = {"name": canonical}
    p.update(
        _rows("select mechanism from drugs where canonical_name = :d", d=canonical)[0]
    )
    p["synonyms"] = [
        r["synonym"]
        for r in _rows(
            "select s.synonym from drug_synonyms s join drugs d on d.id = s.drug_id "
            "where d.canonical_name = :d and s.kind <> 'inn'",
            d=canonical,
        )
    ]
    base = "from trials t join trial_drugs td using (nct_id) join drugs d on d.id = td.drug_id where d.canonical_name = :d"
    p["n_trials"] = _rows(f"select count(distinct t.nct_id) n {base}", d=canonical)[0][
        "n"
    ]
    p["trials_by_phase"] = _rows(
        "select coalesce(ph, 'NO_PHASE') as phase, count(distinct t.nct_id) n "
        "from trials t left join lateral unnest(t.phases) ph on true "
        "join trial_drugs td on td.nct_id = t.nct_id join drugs d on d.id = td.drug_id "
        "where d.canonical_name = :d group by 1 order by 1",
        d=canonical,
    )
    p["trials_by_status"] = _rows(
        f"select t.overall_status as status, count(distinct t.nct_id) n {base} group by 1 order by 2 desc",
        d=canonical,
    )
    p["top_sponsors"] = _rows(
        f"select t.sponsor_name as sponsor, t.sponsor_class, count(distinct t.nct_id) n {base} "
        f"group by 1, 2 order by 3 desc limit 8",
        d=canonical,
    )
    p["n_publications"] = _rows(
        "select count(*) n, count(*) filter (where pd.in_title) n_about from publication_drugs pd "
        "join drugs d on d.id = pd.drug_id where d.canonical_name = :d",
        d=canonical,
    )[0]
    p["top_publications"] = _rows(
        "select p.id, p.title, p.journal, p.pub_year, p.cited_by_count, "
        "'https://europepmc.org/article/' || p.source || '/' || split_part(p.id, ':', 2) as url "
        "from publications p join publication_drugs pd on pd.publication_id = p.id "
        "join drugs d on d.id = pd.drug_id where d.canonical_name = :d and pd.in_title "
        "order by p.cited_by_count desc nulls last limit 5",
        d=canonical,
    )
    p["fda_labels"] = _rows(
        "select l.brand_name, l.generic_name, l.manufacturer, l.effective_date::text as effective_date, "
        "'https://dailymed.nlm.nih.gov/dailymed/lookup.cfm?setid=' || l.set_id as url "
        "from labels l join label_drugs ld using (set_id) join drugs d on d.id = ld.drug_id "
        "where d.canonical_name = :d order by l.effective_date desc",
        d=canonical,
    )
    p["recent_trials"] = list_trials(drug=canonical, limit=10)
    return p


def landscape() -> dict:
    """Panorama competitivo: ensayos por fármaco × fase, estado, año y patrocinador."""
    join = "from trials t join trial_drugs td on td.nct_id = t.nct_id join drugs d on d.id = td.drug_id"
    return {
        "by_phase": _rows(
            f"select d.canonical_name drug, d.mechanism, coalesce(ph, 'NO_PHASE') phase, "
            f"count(distinct t.nct_id) n {join} left join lateral unnest(t.phases) ph on true "
            f"group by 1, 2, 3 order by 1, 3"
        ),
        "active_by_drug": _rows(
            f"select d.canonical_name drug, d.mechanism, count(distinct t.nct_id) n_total, "
            f"count(distinct t.nct_id) filter (where t.overall_status in "
            f"('RECRUITING','NOT_YET_RECRUITING','ACTIVE_NOT_RECRUITING','ENROLLING_BY_INVITATION')) n_active "
            f"{join} group by 1, 2 order by 3 desc"
        ),
        "by_start_year": _rows(
            f"select d.canonical_name drug, extract(year from t.start_date)::int as year, "
            f"count(distinct t.nct_id) n {join} where t.start_date is not null group by 1, 2 order by 2"
        ),
        "top_industry_sponsors": _rows(
            f"select t.sponsor_name sponsor, count(distinct t.nct_id) n {join} "
            f"where t.sponsor_class = 'INDUSTRY' group by 1 order by 2 desc limit 12"
        ),
    }


def health() -> dict:
    return _rows(
        "select (select count(*) from trials) trials, (select count(*) from publications) "
        "publications, (select count(*) from labels) labels"
    )[0]
