# OncoResearchAI

Plataforma de veille concurrentielle en oncología (melanoma): recolecta datos abiertos de
fuentes heterogéneas, los alinea en bases relacional y vectorial, y los consulta con un
agente que responde citando sus fuentes.

Fuentes: ClinicalTrials.gov, Europe PMC, openFDA, ChEMBL y PDFs de congresos.

## Documentación por fases

### Fase 0 — Entorno y exploración

Objetivo: preparar el proyecto y **entender cómo responde cada API** antes de construir nada.

- Proyecto Python con `uv`, `ruff` (estilo) y `pytest` (tests); repositorio git con `.gitignore`
  que deja fuera `.env` y `data/`.
- `docker-compose.yml` con Postgres y Qdrant; configuración leída del `.env` con
  `pydantic-settings`.
- Un *smoke test* por fuente (`scripts/smoke_*.py`): una consulta real, guardando la respuesta
  para inspeccionar su estructura.

Lo que se aprendió:

- Cada API pagina distinto: ClinicalTrials.gov con token (`nextPageToken`), Europe PMC con
  cursor (`cursorMark`), openFDA con offset (`skip`/`limit`) y ChEMBL con `page_meta`.
- Los datos vienen sucios: ruido en las búsquedas, `phases` como lista que puede ser `None`
  o `NA`, fichas de openFDA sin nombre de fármaco, sinónimos de ChEMBL con ruido.
- ChEMBL da errores 500 de forma intermitente, lo que motivó los reintentos.

Decisión de fuentes: ver [`docs/decisions/0001-data-sources.md`](docs/decisions/0001-data-sources.md).

### Fase 1 — Ingestión de datos crudos

Objetivo: convertir los scripts de exploración en una herramienta que descargue **todos** los datos, siempre igual y de forma fiable.

```
landscape.py   → qué estudiamos: melanoma + 10 fármacos
conector       → sabe cómo paginar esa API (uno por fuente)
http.py        → petición con timeout y reintentos
raw_store.py   → guarda cada página tal cual + manifest.json
```

Se ejecuta con `uv run python -m onco_research_ai.ingestion <ctgov|epmc|openfda|chembl|all>`.

Decisiones principales:

- **Una sola capa HTTP** con reintentos con espera creciente, solo ante fallos transitorios
  (5xx, 429, red); un 404 no se reintenta.
- **Conectores como generadores:** entregan una página a la vez, sin cargar todo en memoria.
- **Dato crudo inmutable:** una carpeta nueva por descarga en `data/raw/`; nunca se sobrescribe.
- **`manifest.json` con `status`:** `complete` o `partial`. Una carpeta sin manifiesto es una
  descarga cortada; una parcial terminó pero con errores. `latest_complete_run()` devuelve
  solo la última fiable.
- **Consulta acotada en Europe PMC:** de 69 852 artículos (búsqueda amplia, mucho ruido) a
  3 883 (fármaco y melanoma en título/abstract, 2020-2026).
- **Tests con un servidor HTTP falso** (9 tests): paginación, reintentos y estado de la descarga.

Resultado de la descarga:

| Fuente | Registros | Comprobación |
|---|---|---|
| ClinicalTrials.gov | 3 782 | Coincide con el total de la API, sin duplicados |
| Europe PMC | 3 883 | Sin duplicados |
| openFDA | 48 | Coincide con el total de la API |
| ChEMBL | pendiente | Servidor inestable; repetir cuando responda |

El problema de ChEMBL tuvo dos partes: su servidor estaba degradado (no es nuestro código), y
nuestro conector abortaba toda la descarga por un solo fármaco fallido. Se corrigió para que
registre el error y siga con los demás, y el estado `partial` evita que una descarga fallida
se confunda con una completa. Mientras no haya una descarga completa de ChEMBL, simplemente
no se consulta esa fuente.

### Diferencia entre la Fase 0 y la Fase 1

| | Fase 0 (exploración) | Fase 1 (ingestión) |
|---|---|---|
| Objetivo | Entender cómo responde cada API | Descargar todos los datos |
| Cantidad | 5-10 registros de muestra | Miles de registros |
| Paginación | 2 páginas probadas a mano | Hasta el final, automática |
| Errores | Se rompía (salvo reintento en ChEMBL) | Reintentos y estado de la descarga |
| Guardado | Un JSON suelto | Carpeta por descarga con manifiesto |
| Calidad | Sin tests | 9 tests |
| Uso | Scripts sueltos | Un comando |
| Código | Cada script repetía lo mismo | Pieza común + un conector por fuente |

### Fase 2 — Modelo de datos y alineación

Objetivo: convertir los JSON crudos, cada uno con su formato, en **un catálogo relacional
común** donde se pueda cruzar la información (ensayo ↔ fármaco ↔ artículo).

**Qué contiene cada tabla y de dónde sale**

Cada tabla es una lista de cosas de un mismo tipo. Las tablas de cruce son listas que dicen
«esta cosa va con esta otra».

| Tabla | Origen | Ejemplo de fila |
|---|---|---|
| `trials`, `trial_interventions` | ClinicalTrials.gov (el protocolo que declara el patrocinador) | NCT04657991, fase 3; usa «Encorafenib» |
| `publications` | Europe PMC (registro bibliográfico: título, abstract, revista) | Artículo con su PMID y DOI |
| `labels`, `label_sections` | openFDA (ficha técnica oficial, dividida por secciones) | Ficha de BRAFTOVI → sección «indications_and_usage» |
| `drugs`, `drug_synonyms` | **Escritas a mano** (`processing/drugs_seed.py`); ChEMBL las ampliará | encorafenib ← braftovi, lgx818 |
| `trial_drugs`, `trial_publications`, `publication_drugs`, `label_drugs` | **Calculadas** al cargar, cruzando las anteriores | NCT04657991 ↔ encorafenib |

Cada fila de `trials`, `publications` y `labels` guarda en `source_run` la carpeta de
`data/raw/` de la que salió (trazabilidad).

**Cómo se enlazan las fuentes**

Ninguna fuente comparte clave con las otras, así que el **fármaco es el pivote**: cada fuente
se conecta a `drugs` con el dato que sí trae.

```
Ensayo ──────► Fármaco     ✔ comparando sus intervenciones con los sinónimos
Artículo ────► Fármaco     ✔ sinónimos en título o abstract (`publication_drugs`; `in_title` marca si está en el título)
Ficha FDA ───► Fármaco     ✔ por el bloque `openfda`; si falta, por el texto (`label_drugs`)
Ensayo ◄───► Artículo      ✔ por dos rutas (ver abajo)
```

El enlace ensayo ↔ artículo tiene dos rutas, con distinta fiabilidad (`link_type`):

- `trial_reference`: el ensayo declara el PMID del artículo entre sus referencias (fiable).
- `abstract_mention`: el artículo cita el código NCT en su título o abstract (menos fiable).

Las cifras se pueden comprobar con SQL; por ejemplo, ensayos con algún fármaco:
`select count(distinct nct_id) from trial_drugs;`

**Estado**

- [x] Modelo de datos y tablas en Postgres
- [x] Carga validada con Pydantic: 3 782 ensayos, 3 883 artículos, 48 fichas
  (`uv run python -m onco_research_ai.storage.load`; se puede repetir: vacía y recarga)
- [x] Diccionario de 10 fármacos (36 nombres) y vínculo ensayo ↔ fármaco: 972 ensayos enlazados
- [x] Vínculo ensayo ↔ artículo: 339 por referencia y 282 por mención del NCT
- [x] Artículos ↔ fármacos: 3 865 artículos enlazados (2 190 vínculos con el fármaco en el título)
- [x] Fichas ↔ fármacos: 14 de 48 fichas; las otras 34 son de fármacos fuera de nuestros 10 (dacarbazina, atezolizumab, aldesleukina...)
- [ ] Ampliar sinónimos con ChEMBL (opcional; el diccionario manual basta por ahora)
- [ ] Extractor con LLM de datos en texto libre (línea de tratamiento, ORR, PFS, n)

## Glosario médico y científico

**La enfermedad**

| Término | Significado |
|---|---|
| Melanoma | Cáncer de los melanocitos (células que producen melanina). El cutáneo es el más común; el uveal (ojo) se comporta distinto |
| Metastásico / irresecable | Extendido a otros órganos (estadio IV) o no operable |
| Adyuvante / neoadyuvante | Tratamiento después / antes de la cirugía para evitar la recaída |
| Línea de tratamiento | 1.ª línea = primer tratamiento; 2.ª = el que sigue cuando el primero falla |

**Fármacos y mecanismos**

| Término | Significado |
|---|---|
| BRAF V600E/K | Mutación que deja la proteína BRAF «siempre encendida»; presente en ~50 % de los melanomas |
| MEK | Proteína siguiente a BRAF en la misma vía de señal (MAPK) |
| Inhibidor BRAF (`-fenib`) | encorafenib, dabrafenib, vemurafenib |
| Inhibidor MEK (`-metinib`) | binimetinib, trametinib, cobimetinib |
| Terapia dirigida | Ataca una mutación concreta; rápida, pero el tumor se vuelve resistente |
| Inmunoterapia | Libera los «frenos» (checkpoints) de los linfocitos T: anti-PD-1 (pembrolizumab, nivolumab), anti-CTLA-4 (ipilimumab), anti-LAG-3 (relatlimab) |
| `-mab` | Anticuerpo monoclonal |
| INN / marca / código | Nombre genérico (pembrolizumab) / comercial (Keytruda) / de desarrollo (MK-3475) |

**Ensayos clínicos**

| Término | Significado |
|---|---|
| Fase 1 / 2 / 3 / 4 | Seguridad y dosis / señal de eficacia / comparación con el estándar / vigilancia tras la aprobación |
| Intervencional / observacional | Se asigna un tratamiento / solo se observa (no tiene fase) |
| RCT | Ensayo aleatorizado y controlado; la evidencia más fuerte |
| Patrocinador (sponsor) | Quien financia: `INDUSTRY` (farmacéutica), `NIH`, `OTHER` (hospitales, universidades) |
| Estados | `RECRUITING`, `COMPLETED`, `TERMINATED` (parado antes), `WITHDRAWN` (nunca empezó), `UNKNOWN` |
| Endpoint | La medida principal que el ensayo quiere demostrar |
| NCT | Identificador de un ensayo en ClinicalTrials.gov |

**Medidas de eficacia**

| Sigla | Significado |
|---|---|
| OS | Supervivencia global: cuánto viven los pacientes |
| PFS | Supervivencia libre de progresión: tiempo hasta que la enfermedad avanza o el paciente muere |
| ORR | Tasa de respuesta objetiva: % de pacientes cuyo tumor se reduce (RECIST: ≥ 30 %) |
| HR | Hazard ratio: HR 0,7 = 30 % menos riesgo del evento en un grupo frente al otro |

**Literatura y fichas**

| Término | Significado |
|---|---|
| PMID / DOI | Identificador en PubMed / identificador permanente de cualquier publicación |
| Preprint | Artículo sin revisión por pares (en Europe PMC, `PPR`) |
| Case report | Caso de un solo paciente; evidencia débil |
| Review | Resumen de la literatura existente |
| MeSH | Vocabulario oficial de temas médicos de PubMed |
| Ficha técnica (label) | Documento oficial de la FDA: indicaciones, contraindicaciones, reacciones adversas, estudios clínicos |
