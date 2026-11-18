# ADR 0001 — Data sources

- **Status:** accepted
- **Date:** 2026-11-12
- **Plan phase:** 0 (source exploration)

## Context

The project addresses a competitive-intelligence use case in oncology: aligning structured and
unstructured data from heterogeneous sources to answer questions about the **melanoma**
competitive landscape.

Constraints: open data only, no cost, and a small scope so that every step can be understood
and explained. Selection criterion: **the sources that are simplest to implement and most
important** for the use case.

## Decision

Four public APIs and a manual PDF upload:

| # | Source | Role | Data type |
|---|---|---|---|
| 1 | ClinicalTrials.gov API v2 | Clinical trials (phase, status, sponsor, interventions) | Structured + text |
| 2 | Europe PMC REST | Scientific literature (abstracts) | Unstructured |
| 3 | openFDA `/drug/label` | Labels of approved drugs | Semi-structured |
| 4 | ChEMBL | Dictionary of synonyms and mechanisms of action | Structured (reference) |
| 5 | Manual PDFs (congresses) | Recent data not yet published | Unstructured |

ChEMBL does not provide documents to query: it is the **glue** that makes it possible to
recognize that trials, papers and labels talk about the same drug.

## Rejected alternatives

- **PubMed (E-utilities):** Europe PMC already indexes it; using both would duplicate papers.
- **Open Targets, EMA, FAERS:** useful, but they add complexity without being essential for the
  MVP. They can be added later by reusing the connector pattern.

## Smoke test findings (2026-11-12)

Real queries to the four APIs, without access keys:

| Source | Result | Pagination |
|---|---|---|
| ClinicalTrials.gov | 3,782 trials with condition "melanoma" | `pageToken` (opaque token) |
| Europe PMC | 3,532 papers with `melanoma AND (encorafenib OR binimetinib) AND HAS_ABSTRACT:y` | `cursorMark` |
| openFDA | 48 labels with "melanoma" in the indication | offset: `skip` + `limit` |
| ChEMBL | 5 drugs resolved with synonyms and mechanism; 7,561 mechanisms in total | `page_meta` (offset + `next`) |

### Quality risks detected

1. **Noise in keyword search.** ClinicalTrials.gov returned a "non-melanoma skin cancer" trial
   and a uveal melanoma trial (a different subtype) among the first results. Europe PMC
   returned a paper on lung cancer.
   → Phase 2 must measure and filter this noise.
2. **Optional fields of varying type.** `phases` is a *list* and can be `None` (observational
   studies) or `['NA']` (not applicable). → The schema must tolerate this.
3. **openFDA labels without an `openfda` block.** 3 of 10 inspected labels have no normalized
   drug name (some are old, e.g. 2014). → They cannot be identified by that field.
4. **Versioning in openFDA.** A label has an identity (`set_id`) and several versions.
   → A decision is needed on which one to keep.
5. **Noisy synonyms in ChEMBL.** Combinations such as "Pembrolizumab component of mk-1308a"
   appear. → Filter them before using them for alignment.
6. **ChEMBL returns intermittent 500 errors.** → Connectors must retry with exponential
   backoff (`tenacity`), only on transient errors (5xx, 429, network), never on 4xx.

## Consequences

- The phase 1 connectors share a pattern: request with a *timeout*, selective retries,
  pagination until results are exhausted, and saving the **raw** response in `data/raw/`
  before transforming anything.
- Each source provides a join key (`NCT…`, `PMID`/`DOI`, `set_id`, `CHEMBL…`); the phase 2
  data model is built around those keys.
- The figures above are a snapshot of that date, not a fixed value: the sources are updated
  continuously.
