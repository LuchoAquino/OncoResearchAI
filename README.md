# OncoResearchAI

**Un asistente que responde preguntas sobre el panorama competitivo del melanoma, citando
siempre sus fuentes.**

Los laboratorios farmacéuticos necesitan saber qué están desarrollando sus competidores: qué
ensayos clínicos hay en marcha, qué resultados se han publicado, qué fármacos están aprobados.
Esa información existe en bases de datos públicas, pero está repartida, escrita en formatos
distintos y llena de nombres que se repiten (un mismo fármaco puede aparecer como
«pembrolizumab», «Keytruda» o «MK-3475»).

Este proyecto recoge esos datos, los ordena en un solo catálogo y construirá un asistente de
IA que conteste preguntas como:

> «¿Qué ensayos de fase 3 hay con inmunoterapia anti-PD-1 en melanoma y quién los patrocina?»

El caso de uso está pensado para **encorafenib + binimetinib** (Braftovi + Mektovi, de Pierre
Fabre) frente a sus competidores en melanoma con mutación BRAF.

> Estado: **proyecto en construcción.** Las fases 0 a 3 están hechas (datos descargados,
> ordenados y con controles de calidad). El asistente de IA todavía no existe: ver la hoja de ruta.

## Cómo funciona

```
 Fuentes públicas           Descarga          Catálogo ordenado          Asistente
┌──────────────────┐     ┌───────────┐     ┌────────────────────┐     ┌──────────────┐
│ ClinicalTrials   │     │  JSON     │     │ Base relacional    │     │ Preguntas en │
│ Europe PMC       │ ──► │  crudo    │ ──► │ (Postgres)         │ ──► │ lenguaje     │
│ openFDA          │     │  sin      │     │ + base vectorial   │     │ natural con  │
│ ChEMBL (opcional)│     │  tocar    │     │ (Qdrant)           │     │ citas        │
│ PDFs de congresos│     └───────────┘     └────────────────────┘     └──────────────┘
└──────────────────┘      Fase 1             Fases 2, 3 y 4            Fases 5 a 10
```

- **Base relacional (Postgres):** tablas con filas y columnas. Sirve para preguntas exactas
  («¿cuántos ensayos de fase 3 están reclutando?»).
- **Base vectorial (Qdrant):** guarda el significado de los textos como números, para buscar
  por tema aunque las palabras no coincidan («mecanismos de resistencia a la terapia»).
- **El asistente** decidirá cuál de las dos usar y responderá citando de dónde sacó cada dato.

## Hoja de ruta

| Fase | Qué se hace | Estado |
|---|---|---|
| 0 | Preparar el entorno y explorar cada fuente de datos | ✔ Hecha |
| 1 | Descargar todos los datos de forma fiable | ✔ Hecha (falta ChEMBL, opcional) |
| 2 | Ordenar los datos en tablas y enlazarlos entre sí | ✔ Hecha |
| 3 | Controles de calidad de los datos | ✔ Hecha (falta medir el extractor de IA) |
| 4 | Indexar los textos en la base vectorial | ✔ Hecha con MiniLM y MedCPT (bge-m3 pendiente) |
| 5 | Búsqueda de documentos y su evaluación | Pendiente |
| 6 | Respuestas con citas de las fuentes | Pendiente |
| 7 | Agente que elige cómo buscar | Pendiente |
| 8 | API web y servidor MCP | Pendiente |
| 9 | Interfaz con Streamlit | Pendiente |
| 10 | Evaluación de las respuestas | Pendiente |

## Datos de partida

| Fuente | Qué aporta | Registros descargados |
|---|---|---|
| [ClinicalTrials.gov](https://clinicaltrials.gov) | Ensayos clínicos: fase, estado, patrocinador, tratamientos | 3 782 |
| [Europe PMC](https://europepmc.org) | Artículos científicos: título, resumen, revista, año | 3 883 |
| [openFDA](https://open.fda.gov) | Fichas técnicas oficiales de fármacos aprobados | 48 |
| [ChEMBL](https://www.ebi.ac.uk/chembl/) | Nombres alternativos de cada fármaco | Pendiente (servidor inestable) |
| PDFs de congresos | Resultados aún no publicados, cargados a mano | Pendiente |

Alcance: melanoma y 10 fármacos (encorafenib, binimetinib, dabrafenib, trametinib,
vemurafenib, cobimetinib, pembrolizumab, nivolumab, ipilimumab, relatlimab).
Por qué estas fuentes y no otras: [`docs/decisions/0001-data-sources.md`](docs/decisions/0001-data-sources.md).

## Cómo ejecutarlo

Necesitas Docker, [`uv`](https://docs.astral.sh/uv/) y Python 3.12.

```bash
cp .env.example .env              # y rellena las contraseñas (y GROQ_API_KEY para el paso 5)
docker compose up -d              # 1. arranca Postgres y Qdrant
uv sync                           # 2. instala las dependencias
uv run python -m onco_research_ai.ingestion all          # 3. descarga los datos a data/raw/
uv run python -m onco_research_ai.storage.load           # 4. los carga en Postgres
uv run python -m onco_research_ai.processing.extractor --limit 20   # 5. extractor de IA (opcional)
uv run python -m onco_research_ai.quality.checks         # 6. informe de calidad
uv run python -m onco_research_ai.retrieval.index --model minilm   # 7. indexa en Qdrant (6 min en GPU); también: medcpt (35 min), bge-m3 (~100 min)
uv run python -m onco_research_ai.retrieval.search "resistance to BRAF inhibitors" --model minilm   # 8. prueba de búsqueda
uv run pytest                     # tests
```

Los pasos 3 y 4 se pueden repetir sin riesgo: el 3 crea una descarga nueva sin borrar las
anteriores y el 4 vacía las tablas y las recarga desde los datos descargados.
La clave gratuita para el paso 5 se obtiene en [console.groq.com](https://console.groq.com).

## Estructura del proyecto

```
src/onco_research_ai/
  ingestion/    descarga de cada fuente (un conector por API)
  processing/   limpieza, validación, diccionario de fármacos y extractor de IA
  storage/      tablas de Postgres y carga de datos
  quality/      controles de calidad
  retrieval/    embeddings, indexación en Qdrant y búsqueda
docs/decisions/ por qué se eligió cada herramienta o fuente
eval/reports/   informes de calidad generados
scripts/        pruebas rápidas de cada API
tests/          tests automáticos
data/           datos descargados (no se suben a git)
```

---

# Documentación por fases

## Fase 0 — Entorno y exploración

**Objetivo:** preparar el proyecto y entender cómo responde cada API antes de construir nada.

- Proyecto Python con `uv` (dependencias), `ruff` (estilo) y `pytest` (tests); `.gitignore`
  deja fuera las contraseñas (`.env`) y los datos (`data/`).
- `docker-compose.yml` levanta Postgres y Qdrant con un comando.
- Una prueba rápida por fuente (`scripts/smoke_*.py`): una consulta real para ver cómo
  vienen los datos.

Lo que se aprendió:

- Cada API reparte los resultados en páginas de forma distinta: ClinicalTrials.gov con un token
  (`nextPageToken`), Europe PMC con un cursor (`cursorMark`), openFDA con un desplazamiento
  (`skip`/`limit`) y ChEMBL con un bloque `page_meta`.
- Los datos vienen sucios: resultados que no son de melanoma, fases de ensayo vacías o
  marcadas `NA`, fichas de openFDA sin nombre de fármaco, sinónimos de ChEMBL con ruido.
- ChEMBL da errores 500 de forma intermitente.

## Fase 1 — Descarga de datos

**Objetivo:** convertir las pruebas en una herramienta que descargue **todos** los datos, siempre
igual y de forma fiable.

```
landscape.py   → qué estudiamos: melanoma + 10 fármacos
conector       → sabe cómo paginar esa API (uno por fuente)
http.py        → petición con tiempo máximo y reintentos
raw_store.py   → guarda cada página tal cual + un manifest.json
```

Decisiones principales:

- **Reintentos con espera creciente**, solo ante fallos pasajeros (error 5xx, límite de
  peticiones, red caída). Un 404 no se reintenta: repetirlo no lo arregla.
- **Los datos crudos no se tocan:** cada descarga va a una carpeta nueva en `data/raw/` y nunca
  se sobrescribe. Si algo sale mal más adelante, se puede volver a empezar desde ahí.
- **`manifest.json` con estado:** `complete` o `partial`. Una carpeta sin manifiesto es una
  descarga cortada; una `partial` terminó pero con errores. Solo se usa la última `complete`.
- **Búsqueda acotada en Europe PMC:** de 69 852 artículos (búsqueda amplia, mucho ruido) a
  3 883 (fármaco y melanoma en título o resumen, de 2020 en adelante).
- **Tests con un servidor HTTP falso** para probar paginación y reintentos sin depender de internet.

| Fuente | Registros | Comprobación |
|---|---|---|
| ClinicalTrials.gov | 3 782 | Coincide con el total que declara la API, sin duplicados |
| Europe PMC | 3 883 | Sin duplicados |
| openFDA | 48 | Coincide con el total de la API |
| ChEMBL | pendiente | Servidor inestable; si no responde, simplemente no se usa esa fuente |

**Diferencia entre las fases 0 y 1:**

| | Fase 0 (exploración) | Fase 1 (descarga) |
|---|---|---|
| Objetivo | Entender cómo responde cada API | Descargar todos los datos |
| Cantidad | 5-10 registros de muestra | Miles de registros |
| Paginación | 2 páginas probadas a mano | Hasta el final, automática |
| Errores | Se rompía | Reintentos y estado de la descarga |
| Uso | Scripts sueltos | Un comando |

## Fase 2 — Modelo de datos y alineación

**Objetivo:** convertir los JSON crudos, cada uno con su formato, en **un catálogo único** donde
se pueda cruzar la información (ensayo ↔ fármaco ↔ artículo).

### Qué contiene cada tabla y de dónde sale

Cada tabla es una lista de cosas del mismo tipo. Las «tablas de cruce» son listas que dicen
«esta cosa va con esta otra».

| Tabla | Origen | Ejemplo de fila |
|---|---|---|
| `trials`, `trial_interventions` | ClinicalTrials.gov (lo que declara el patrocinador antes del ensayo) | NCT04657991, fase 3; usa «Encorafenib» |
| `publications` | Europe PMC (registro bibliográfico: título, resumen, revista) | Un artículo con su PMID y DOI |
| `labels`, `label_sections` | openFDA (ficha técnica oficial, dividida por secciones) | Ficha de BRAFTOVI → sección «indicaciones» |
| `drugs`, `drug_synonyms` | **Escritas a mano** en `processing/drugs_seed.py` | encorafenib ← braftovi, lgx818 |
| `trial_drugs`, `publication_drugs`, `label_drugs`, `trial_publications` | **Calculadas** al cargar, cruzando las anteriores | NCT04657991 ↔ encorafenib |
| `publication_extractions` | **Generada por IA** a partir del resumen de cada artículo | Un artículo → n = 270, PFS = 14,9 meses |

Cada fila guarda en `source_run` la carpeta de `data/raw/` de la que salió, así siempre se
puede rastrear su origen.

### Cómo se enlazan las fuentes

Las tres fuentes no comparten ningún identificador, así que el **fármaco hace de punto de
unión**: cada fuente se conecta a la tabla `drugs` con el dato que sí trae.

```
Ensayo ──────► Fármaco     comparando sus tratamientos con los nombres conocidos del fármaco
Artículo ────► Fármaco     buscando esos nombres en el título y el resumen (in_title marca si está en el título)
Ficha FDA ───► Fármaco     por el nombre de la ficha; si falta, buscando en su texto
Ensayo ◄───► Artículo      por dos rutas (abajo)
```

Enlace ensayo ↔ artículo, con dos niveles de fiabilidad (`link_type`):

- `trial_reference`: el propio ensayo declara el artículo entre sus referencias (fiable).
- `abstract_mention`: el artículo cita el código NCT del ensayo en su título o resumen (menos fiable).

Con esto, un solo cruce por `drugs` responde: «dame los ensayos, artículos y fichas de pembrolizumab».

### Limitaciones conocidas

- Solo se enlazan los 10 fármacos del diccionario. Las fichas de otros fármacos (dacarbazina,
  atezolizumab…) quedan sueltas: 34 de las 48.
- Un artículo enlazado por el resumen puede mencionar el fármaco solo de pasada; por eso existe `in_title`.
- 21 de las 48 fichas no traen nombre de fármaco como dato aparte.

### El extractor de IA y las alucinaciones

Algunos datos clave (número de pacientes, supervivencia, línea de tratamiento) solo aparecen
dentro del texto libre de los resúmenes. Un modelo de lenguaje (`gpt-oss-120b` de Groq, a través
de LiteLLM) los lee y rellena un formulario fijo. Pero un modelo puede **inventar** un dato, así
que hay tres defensas:

1. El prompt exige `null` si el dato no aparece.
2. Pydantic rechaza valores fuera del formulario (por ejemplo, una línea de tratamiento inexistente).
3. Cada cifra devuelta debe aparecer **literalmente** en el resumen; si no, queda anotada en `unverified_fields`.

Ejemplo real: el estudio CheckMate 067 da tres grupos (n = 314, 316 y 315) y el modelo devolvió
n = 945, la suma. Es correcto, pero no está escrito, así que quedó marcado como no verificado.
Esta tabla no se vacía al recargar los datos, porque cada extracción consume cuota de la API.

### Estado

- [x] Modelo de datos y tablas en Postgres
- [x] Carga validada con Pydantic: 3 782 ensayos, 3 838 artículos (tras quitar duplicados), 48 fichas
- [x] Diccionario de 10 fármacos (36 nombres) y enlaces con ensayos, artículos y fichas
- [x] Extractor de IA probado con 47 artículos
- [ ] Ampliar el diccionario con ChEMBL (opcional)

## Fase 3 — Calidad de datos

**Objetivo:** saber **cuánto fiarse** de los datos cargados. Cada control es una consulta SQL
con nombre y explicación (`quality/checks.py`), y el informe se guarda en `eval/reports/`.

| Tipo | Pregunta | Ejemplo |
|---|---|---|
| Completitud | ¿Cuántos datos faltan? | 1,0 % de ensayos sin fecha de inicio; 43,8 % de fichas sin nombre de marca |
| Consistencia | ¿Hay datos imposibles? (debe ser 0) | Un ensayo que termina antes de empezar |
| Duplicados | ¿Hay algo repetido? (debe ser 0) | El mismo artículo como preprint y como versión publicada |
| Pertinencia | ¿Cuánto es ruido? | 8,8 % de ensayos no nombra «melanoma» (suelen ser genéricos: «Solid Tumors») |
| Alineación | ¿Qué parte quedó enlazada? | 25,7 % de ensayos con fármaco; 99,5 % de artículos |

Lo que encontró el primer informe:

- **Falsa alarma:** 139 ensayos con tamaño 0. Eran todos `WITHDRAWN` (cancelados antes de
  reclutar a nadie), donde 0 es correcto. Se corrigió el control, no los datos.
- **Duplicados reales:** el mismo artículo como preprint y como versión publicada, con DOI
  distinto. Se detectan por título y año, y se conserva la versión de PubMed (45 eliminados).
  Una primera versión conservaba registros de Agricola sin DOI; se detectó al revisar a mano
  qué se eliminaba.
- Solo el 6,3 % de los ensayos tiene un artículo enlazado: el enlace es fiable pero escaso.

**Pendiente:** medir qué porcentaje de las extracciones de la IA son correctas, comparándolas
con una muestra revisada a mano.

## Fase 4 — Indexación vectorial

**Objetivo:** que se pueda buscar por **significado** y no solo por palabras exactas.

```
Postgres ─► chunking.py ─► embedder.py ─► vectorstore.py (Qdrant)
 filas       trozos de       vectores        colección con vectores
            ≤180 tokens     de 384 números  + metadatos para filtrar y citar
```

### Conceptos

- **Embedding:** un texto convertido en una lista de números (384 con MiniLM, 1 024 con
  bge-m3). Los textos de significado parecido quedan cerca. Con MiniLM, dos frases sobre el
  mismo tratamiento escritas con palabras distintas puntúan 0,68; una frase y una receta de
  cocina, −0,06.
- **Similitud coseno:** mide el ángulo entre dos vectores (1 = misma dirección, 0 = sin relación).
- **Token:** el modelo no lee palabras sino trozos de palabra. «encorafenib» se rompe en 5
  trozos (`en ##cor ##af ##eni ##b`): un modelo general apenas conoce los nombres de fármacos.
- **Límite de tokens:** MiniLM lee como máximo 256 tokens y descarta el resto sin avisar. El
  86,7 % de los abstracts lo superan (mediana: 402), así que se pierde casi siempre la segunda
  mitad, donde están los resultados.
- **Chunking:** por eso los textos se trocean (≤180 tokens, cortando entre frases y con una
  frase de solapamiento). Además, un vector por trozo es más preciso que uno por abstract
  completo, que mezcla varias ideas.
- **Qdrant:** base de datos de vectores. Cada trozo es un *punto* (vector + *payload* con
  metadatos) dentro de una *colección*. El payload permite combinar significado y filtros
  exactos: «los trozos más parecidos a mi pregunta, pero solo ensayos de fase 3 con encorafenib».
- **HNSW:** índice que evita comparar con todos los vectores. Con 25 000 trozos Qdrant aún
  compara con todos (es instantáneo); el índice solo importa con millones.

**¿Por qué Qdrant y no Chroma, FAISS o pgvector?** Con este volumen cualquiera valdría. Se
eligió Qdrant porque funciona como un servidor independiente, filtra por metadatos y admite
búsqueda híbrida (palabras exactas + significado), que es como se hace en producción. Chroma es
más sencillo y bueno para prototipos; FAISS es solo una librería de índices; pgvector guarda los
vectores dentro de Postgres.

### Qué se indexa

| Origen | Cómo se trocea | Trozos | Metadatos (payload) |
|---|---|---|---|
| Ensayos | título + resumen | 5 542 | fase, estado, patrocinador, año, fármacos, enlace |
| Artículos | abstract en trozos, con el título delante de cada uno | 12 404 | año, revista, fármacos, enlace |
| Fichas FDA | cada sección en trozos con el nombre del fármaco delante | 7 130 | sección, fármacos, enlace |
| **Total** | | **25 076** | |

El identificador de cada trozo se calcula a partir del documento y su posición, así que
reindexar sobrescribe en vez de duplicar. Indexar con MiniLM en una GTX 1650 tarda unos 6 minutos.

### Modelos indexados

Los dos modelos usan exactamente los mismos 25 076 trozos (se trocea con un tokenizador común),
para poder compararlos con justicia en la fase 5.

| Modelo | Tipo | Vector | Tiempo de indexación (GTX 1650) |
|---|---|---|---|
| MiniLM (`all-MiniLM-L6-v2`) | General, 22 M parámetros | 384 | 6 min |
| MedCPT (NCBI) | Biomédico, entrenado con búsquedas de PubMed; usa un modelo para los textos y otro para las preguntas | 768 | 34,5 min |
| bge-m3 | General multilingüe, 570 M parámetros | 1 024 | Pendiente (~100 min estimados) |

### Ejemplos de búsqueda

| Pregunta | Resultado |
|---|---|
| «how do melanoma cells become resistant to BRAF inhibitors» | Tres revisiones sobre resistencia a BRAF, aunque ninguna usa esas palabras exactas |
| «recommended dose of encorafenib» (sin filtro) | Salió la ficha de MEKTOVI, que solo cita a encorafenib de pasada |
| La misma, con filtro `--drug encorafenib` | Salen las secciones de dosis de la ficha de BRAFTOVI |
| «MK-3475» | Encuentra los ensayos que escriben ese código, pero no los de pembrolizumab que usan el nombre; y los resultados 3.º y 4.º ya no tienen relación |

El último caso es la limitación esperada de la búsqueda por significado con nombres propios, y
es la razón de la búsqueda híbrida (BM25 + vectores) de la fase 5.

---

# Glosarios

## Glosario técnico

| Término | Significado |
|---|---|
| API | Forma que ofrece un sitio web para que un programa le pida datos |
| Paginación | Repartir un resultado grande en trozos («páginas») |
| JSON | Formato de texto para guardar datos estructurados |
| Pipeline | Cadena de pasos: descargar → limpiar → guardar → consultar |
| Base relacional | Datos en tablas con filas y columnas, consultables con SQL |
| Base vectorial | Guarda el significado de un texto como números para buscar por parecido |
| Tabla de cruce | Tabla que enlaza dos tablas («este ensayo usa este fármaco») |
| Embedding | Texto convertido en una lista de números que representa su significado |
| Token | Trozo de palabra que lee un modelo; los límites de longitud se miden en tokens |
| Chunk | Fragmento de un texto largo, del tamaño que cabe en el modelo |
| LLM | Modelo de lenguaje (tipo ChatGPT) |
| Alucinación | Cuando un LLM inventa algo que no está en la fuente |
| RAG | Que el LLM conteste usando documentos buscados antes, y los cite |
| Pydantic | Librería que valida que un dato tenga el formato esperado |
| Docker | Programa que ejecuta servicios (como Postgres) sin instalarlos a mano |

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
