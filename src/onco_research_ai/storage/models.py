"""Modelo relacional. Una tabla por entidad; las tablas de cruce enlazan fuentes entre sí.

Convenciones:
- `source_run` guarda la carpeta de datos crudos de la que salió cada fila (trazabilidad).
- Los campos que pueden faltar en la fuente son `| None`: lo desconocido es NULL, no "".
"""

from datetime import date

from sqlalchemy import ARRAY, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------- ensayos clínicos
class Trial(Base):
    __tablename__ = "trials"

    nct_id: Mapped[str] = mapped_column(String(11), primary_key=True)
    brief_title: Mapped[str] = mapped_column(Text)
    official_title: Mapped[str | None] = mapped_column(Text)
    brief_summary: Mapped[str | None] = mapped_column(Text)
    study_type: Mapped[str | None] = mapped_column(String(32))
    overall_status: Mapped[str | None] = mapped_column(String(32))
    # Lista: ['PHASE1','PHASE2'] = ensayo fase 1/2. Vacía = estudio sin fases (observacional).
    phases: Mapped[list[str]] = mapped_column(ARRAY(String(16)), default=list)
    conditions: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    sponsor_name: Mapped[str | None] = mapped_column(Text)
    sponsor_class: Mapped[str | None] = mapped_column(
        String(16)
    )  # INDUSTRY, NIH, OTHER...
    # La API da fechas parciales ("2024-05"); se guardan como el primer día del mes.
    start_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    enrollment: Mapped[int | None] = mapped_column(Integer)
    has_results: Mapped[bool] = mapped_column(Boolean, default=False)
    source_run: Mapped[str] = mapped_column(String(64))

    interventions: Mapped[list["TrialIntervention"]] = relationship(
        back_populates="trial", cascade="all, delete-orphan"
    )


class TrialIntervention(Base):
    __tablename__ = "trial_interventions"

    id: Mapped[int] = mapped_column(primary_key=True)
    nct_id: Mapped[str] = mapped_column(
        ForeignKey("trials.nct_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str | None] = mapped_column(
        String(32)
    )  # DRUG, BIOLOGICAL, PROCEDURE...
    other_names: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    trial: Mapped[Trial] = relationship(back_populates="interventions")


# ---------------------------------------------------------------- literatura
class Publication(Base):
    __tablename__ = "publications"

    # "MED:42678759", "PPR:PPR123"...  PMID y DOI pueden faltar (preprints), así que
    # ninguno sirve de clave primaria.
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    source: Mapped[str] = mapped_column(String(8))
    pmid: Mapped[str | None] = mapped_column(String(16), index=True)
    doi: Mapped[str | None] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(Text)
    abstract: Mapped[str | None] = mapped_column(Text)
    journal: Mapped[str | None] = mapped_column(Text)
    pub_year: Mapped[int | None] = mapped_column(Integer, index=True)
    pub_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    is_open_access: Mapped[bool] = mapped_column(Boolean, default=False)
    cited_by_count: Mapped[int | None] = mapped_column(Integer)
    source_run: Mapped[str] = mapped_column(String(64))


# ---------------------------------------------------------------- fichas técnicas (FDA)
class Label(Base):
    __tablename__ = "labels"

    set_id: Mapped[str] = mapped_column(
        String(64), primary_key=True
    )  # identidad de la ficha
    version: Mapped[int | None] = mapped_column(Integer)
    effective_date: Mapped[date | None] = mapped_column(Date)
    # Solo existen si la ficha trae el bloque `openfda` (en ~44 % de los casos NO lo trae).
    generic_name: Mapped[str | None] = mapped_column(Text)
    brand_name: Mapped[str | None] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    source_run: Mapped[str] = mapped_column(String(64))

    sections: Mapped[list["LabelSection"]] = relationship(
        back_populates="label", cascade="all, delete-orphan"
    )


class LabelSection(Base):
    """Una fila por sección (indications_and_usage, clinical_studies...): ya listas para trocear."""

    __tablename__ = "label_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    set_id: Mapped[str] = mapped_column(
        ForeignKey("labels.set_id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(128))
    text: Mapped[str] = mapped_column(Text)

    label: Mapped[Label] = relationship(back_populates="sections")


# ---------------------------------------------------------------- fármacos (alineación)
class Drug(Base):
    __tablename__ = "drugs"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(
        String(128), unique=True
    )  # nombre INN en minúscula
    chembl_id: Mapped[str | None] = mapped_column(
        String(32), unique=True
    )  # llega con ChEMBL
    mechanism: Mapped[str | None] = mapped_column(Text)

    synonyms: Mapped[list["DrugSynonym"]] = relationship(
        back_populates="drug", cascade="all, delete-orphan"
    )


class DrugSynonym(Base):
    __tablename__ = "drug_synonyms"

    id: Mapped[int] = mapped_column(primary_key=True)
    drug_id: Mapped[int] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), index=True
    )
    synonym: Mapped[str] = mapped_column(String(256), index=True)  # en minúscula
    kind: Mapped[str] = mapped_column(String(16))  # inn | brand | code | other
    source: Mapped[str] = mapped_column(String(16))  # manual | chembl | openfda

    drug: Mapped[Drug] = relationship(back_populates="synonyms")


# ---------------------------------------------------------------- tablas de cruce
class TrialPublication(Base):
    __tablename__ = "trial_publications"

    nct_id: Mapped[str] = mapped_column(
        ForeignKey("trials.nct_id", ondelete="CASCADE"), primary_key=True
    )
    publication_id: Mapped[str] = mapped_column(
        ForeignKey("publications.id", ondelete="CASCADE"), primary_key=True
    )
    # CÓMO se enlazó: "abstract_mention" (el artículo cita el NCT) o "trial_reference"
    # (el ensayo lista el artículo entre sus referencias). Permite medir la fiabilidad.
    link_type: Mapped[str] = mapped_column(String(24), primary_key=True)


class TrialDrug(Base):
    __tablename__ = "trial_drugs"

    nct_id: Mapped[str] = mapped_column(
        ForeignKey("trials.nct_id", ondelete="CASCADE"), primary_key=True
    )
    drug_id: Mapped[int] = mapped_column(
        ForeignKey("drugs.id", ondelete="CASCADE"), primary_key=True
    )
    matched_text: Mapped[str] = mapped_column(
        Text
    )  # qué texto del ensayo provocó el vínculo
