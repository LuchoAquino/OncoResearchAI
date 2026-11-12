"""Del JSON crudo de cada API a objetos validados con Pydantic (el contrato de entrada a la BD)."""

import re
from datetime import date

from pydantic import BaseModel, Field

# Secciones de la ficha FDA que nos interesan (el resto es logística: envase, instrucciones...).
LABEL_SECTIONS = [
    "indications_and_usage",
    "dosage_and_administration",
    "contraindications",
    "warnings_and_cautions",
    "adverse_reactions",
    "mechanism_of_action",
    "clinical_studies",
]


def parse_partial_date(value: str | None) -> date | None:
    """'2024-05-31' -> 2024-05-31; '2024-05' -> 2024-05-01; '20260507' -> 2026-05-07."""
    if not value:
        return None
    digits = value.replace("-", "")
    try:
        if len(digits) == 6:  # año-mes
            return date(int(digits[:4]), int(digits[4:6]), 1)
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def strip_html(text: str | None) -> str | None:
    """Europe PMC mete etiquetas (<h4>Background</h4>) en los abstracts."""
    if not text:
        return None
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip() or None


class InterventionIn(BaseModel):
    name: str
    type: str | None = None
    other_names: list[str] = Field(default_factory=list)


class TrialIn(BaseModel):
    nct_id: str
    brief_title: str
    official_title: str | None = None
    brief_summary: str | None = None
    study_type: str | None = None
    overall_status: str | None = None
    phases: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    sponsor_name: str | None = None
    sponsor_class: str | None = None
    start_date: date | None = None
    completion_date: date | None = None
    enrollment: int | None = None
    has_results: bool = False
    interventions: list[InterventionIn] = Field(default_factory=list)
    reference_pmids: list[str] = Field(
        default_factory=list
    )  # solo para enlazar, no se guarda

    @classmethod
    def from_raw(cls, study: dict) -> "TrialIn":
        p = study["protocolSection"]
        ident, status = p["identificationModule"], p.get("statusModule", {})
        design = p.get("designModule", {})
        sponsor = p.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {})
        return cls(
            nct_id=ident["nctId"],
            brief_title=ident["briefTitle"],
            official_title=ident.get("officialTitle"),
            brief_summary=p.get("descriptionModule", {}).get("briefSummary"),
            study_type=design.get("studyType"),
            overall_status=status.get("overallStatus"),
            phases=design.get("phases") or [],  # vacío = sin fases (observacional)
            conditions=p.get("conditionsModule", {}).get("conditions", []),
            sponsor_name=sponsor.get("name"),
            sponsor_class=sponsor.get("class"),
            start_date=parse_partial_date(
                status.get("startDateStruct", {}).get("date")
            ),
            completion_date=parse_partial_date(
                status.get("completionDateStruct", {}).get("date")
            ),
            enrollment=design.get("enrollmentInfo", {}).get("count"),
            has_results=bool(study.get("hasResults")),
            interventions=[
                InterventionIn(
                    name=i["name"],
                    type=i.get("type"),
                    other_names=i.get("otherNames", []),
                )
                for i in p.get("armsInterventionsModule", {}).get("interventions", [])
            ],
            reference_pmids=[
                r["pmid"]
                for r in p.get("referencesModule", {}).get("references", [])
                if r.get("pmid")
            ],
        )


class PublicationIn(BaseModel):
    id: str
    source: str
    pmid: str | None = None
    doi: str | None = None
    title: str
    abstract: str | None = None
    journal: str | None = None
    pub_year: int | None = None
    pub_types: list[str] = Field(default_factory=list)
    is_open_access: bool = False
    cited_by_count: int | None = None

    @classmethod
    def from_raw(cls, r: dict) -> "PublicationIn":
        year = r.get("pubYear")
        return cls(
            id=f"{r['source']}:{r['id']}",
            source=r["source"],
            pmid=r.get("pmid"),
            doi=(r.get("doi") or "").lower() or None,
            title=strip_html(r.get("title")) or "",
            abstract=strip_html(r.get("abstractText")),
            journal=r.get("journalInfo", {}).get("journal", {}).get("title"),
            pub_year=int(year) if year else None,
            pub_types=r.get("pubTypeList", {}).get("pubType", []),
            is_open_access=r.get("isOpenAccess") == "Y",
            cited_by_count=int(r["citedByCount"]) if r.get("citedByCount") else None,
        )


class LabelIn(BaseModel):
    set_id: str
    version: int | None = None
    effective_date: date | None = None
    generic_name: str | None = None
    brand_name: str | None = None
    manufacturer: str | None = None
    sections: dict[str, str] = Field(default_factory=dict)

    @classmethod
    def from_raw(cls, r: dict) -> "LabelIn":
        ofda = r.get("openfda", {})  # ausente en ~44 % de las fichas
        first = lambda key: (ofda.get(key) or [None])[0]
        return cls(
            set_id=r["set_id"],
            version=int(r["version"]) if r.get("version") else None,
            effective_date=parse_partial_date(r.get("effective_time")),
            generic_name=first("generic_name"),
            brand_name=first("brand_name"),
            manufacturer=first("manufacturer_name"),
            sections={k: " ".join(r[k]) for k in LABEL_SECTIONS if r.get(k)},
        )
