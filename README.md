# OncoResearchAI

**Un asistente que responde preguntas sobre el panorama competitivo del melanoma, citando
siempre sus fuentes.**

Los laboratorios farmacéuticos necesitan saber qué están desarrollando sus competidores: qué
ensayos clínicos hay en marcha, qué resultados se han publicado, qué fármacos están aprobados.
Esa información existe en bases de datos públicas, pero está repartida, escrita en formatos
distintos y llena de nombres que se repiten (un mismo fármaco puede aparecer como
«pembrolizumab», «Keytruda» o «MK-3475»).

Este proyecto recoge esos datos, los ordena en un solo catálogo y ofrece un asistente de IA
que contesta preguntas como:

> «¿Qué ensayos de fase 3 con encorafenib están activos y qué comparan?»
> «¿Qué fármaco anti-PD-1 tiene más ensayos de fase 3?»
> «What are the main mechanisms of resistance to BRAF inhibitors?»

y responde **citando cada afirmación** con un enlace a su fuente (ensayo, artículo, ficha FDA o
PDF de congreso). El caso de uso está pensado para **encorafenib + binimetinib** (Braftovi +
Mektovi, de Pierre Fabre) frente a sus competidores en melanoma.

> Estado: **funcional de punta a punta** (fases 0-10). Pendientes que necesitan revisión
> humana: medir el extractor de IA con una muestra anotada y revisar el conjunto de evaluación.

## Cómo funciona

```
 Fuentes públicas          Catálogo                        Asistente                 Uso
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────────────────┐   ┌───────────┐
│ ClinicalTrials   │   │ Postgres         │   │ 1. Planifica: ¿datos exactos │   │ Streamlit │
│ Europe PMC       │──►│ (tablas+enlaces) │──►│    (SQL) o contenido         │──►│ API REST  │
│ openFDA          │   │ Qdrant (vectores)│   │    (búsqueda)?               │   │ MCP       │
│ PDFs congresos   │   │ BM25 (palabras)  │   │ 2. Busca / consulta          │   │ (agentes) │
└──────────────────┘   └──────────────────┘   │ 3. Responde citando [S1]     │   └───────────┘
                                              │ 4. Verifica citas y números  │
                                              └──────────────────────────────┘
```

- **Postgres (base relacional):** responde preguntas exactas («¿cuántos ensayos de fase 3
  están reclutando?») con SQL que el agente escribe y que se valida antes de ejecutarlo.
- **Qdrant + BM25 (búsqueda híbrida):** encuentra textos por significado *y* por palabras
  exactas (nombres de fármacos, códigos como MK-3475), y un reranker reordena los mejores.
- **El agente (LangGraph)** decide qué usar, responde solo con lo encontrado y comprueba que
  cada cita exista y que cada número aparezca en las fuentes; si no, reescribe la respuesta.

## Resultados principales

| Qué se midió | Resultado | Detalle |
|---|---|---|
| Búsqueda: el documento correcto entre los 5 primeros | **87 %** (102 preguntas) | Fase 5 |
| Búsqueda: preguntas en español | 74 % (el agente traduce al inglés antes de buscar) | Fase 5 |
| Respuestas: dato correcto en preguntas con respuesta conocida | 4 de 4 | Fase 10 |
| Respuestas: afirmaciones respaldadas por sus fuentes (LLM juez) | 84 % (12 preguntas) | Fase 10 |
| Tiempo de respuesta | ~2 s búsqueda · ~5-20 s respuesta completa | GTX 1650 + Groq gratis |

## Hoja de ruta

| Fase | Qué se hace | Estado |
|---|---|---|
| 0 | Preparar el entorno y explorar cada fuente de datos | ✔ |
| 1 | Descargar todos los datos de forma fiable | ✔ (ChEMBL opcional, servidor inestable) |
| 2 | Ordenar los datos en tablas y enlazarlos entre sí | ✔ |
| 3 | Controles de calidad de los datos | ✔ (falta medir el extractor con anotación manual) |
| 4 | Indexar los textos en la base vectorial | ✔ MiniLM y MedCPT (bge-m3 opcional) |
| 5 | Búsqueda híbrida y su evaluación | ✔ |
| 6 | Respuestas con citas de las fuentes | ✔ |
| 7 | Agente que elige cómo buscar (LangGraph) | ✔ |
| 8 | API REST y servidor MCP | ✔ |
| 9 | Interfaz con Streamlit | ✔ |
| 10 | Evaluación de las respuestas + PDFs de congresos | ✔ |

## Datos de partida

| Fuente | Qué aporta | Registros |
|---|---|---|
| [ClinicalTrials.gov](https://clinicaltrials.gov) | Ensayos clínicos: fase, estado, patrocinador, tratamientos | 3 782 |
| [Europe PMC](https://europepmc.org) | Artículos científicos: título, resumen, revista, año | 3 838 (tras quitar duplicados) |
| [openFDA](https://open.fda.gov) | Fichas técnicas oficiales de fármacos aprobados | 48 |
| [ChEMBL](https://www.ebi.ac.uk/chembl/) | Nombres alternativos de cada fármaco | Opcional (servidor inestable) |
| PDFs de congresos | Resultados aún no publicados, cargados a mano | Listo para usar (`data/manual_pdfs/`) |

Alcance: melanoma y 10 fármacos (encorafenib, binimetinib, dabrafenib, trametinib,
vemurafenib, cobimetinib, pembrolizumab, nivolumab, ipilimumab, relatlimab).
Por qué estas fuentes y no otras: [`docs/decisions/0001-data-sources.md`](docs/decisions/0001-data-sources.md).

## Cómo ejecutarlo

Necesitas Docker, [`uv`](https://docs.astral.sh/uv/), Python 3.12, una GPU NVIDIA (recomendada,
no obligatoria) y una clave gratuita de Groq ([console.groq.com](https://console.groq.com)).

```bash
cp .env.example .env     # rellena las contraseñas de Postgres y GROQ_API_KEY
make install             # dependencias
make pipeline            # Docker + descarga + carga en Postgres + calidad + índices (~15 min)
make api                 # terminal 1: API en http://localhost:8000/docs
make ui                  # terminal 2: interfaz en http://localhost:8501
```

`make help` lista todos los comandos (evaluaciones, PDFs, MCP, tests...). La primera
pregunta tarda más porque descarga y carga los modelos de Hugging Face.

**Usarlo desde Claude (MCP).** El servidor MCP expone 5 herramientas (`search_evidence`,
`query_trials`, `get_drug_profile`, `get_landscape`, `ask`). En Claude Code:

```bash
claude mcp add oncoresearchai -- uv --directory /ruta/a/OncoResearchAI run python -m onco_research_ai.mcp_server.server
```

En Claude Desktop, en `claude_desktop_config.json`:

```json
{"mcpServers": {"oncoresearchai": {"command": "uv", "args": ["--directory", "/ruta/a/OncoResearchAI",
  "run", "python", "-m", "onco_research_ai.mcp_server.server"]}}}
```

**Añadir PDFs de congresos:** copia los PDF en `data/manual_pdfs/`, opcionalmente un
`metadata.csv` (`file,title,congress,year,url`), y ejecuta `make pdfs`.

## Estructura del proyecto

```
src/onco_research_ai/
  ingestion/    descarga de cada fuente (un conector por API) y PDFs de congresos
  processing/   limpieza, validación, diccionario de fármacos, troceado y extractor de IA
  storage/      tablas de Postgres, carga de datos, consultas fijas y acceso a Qdrant
  quality/      controles de calidad
  retrieval/    embeddings, indexación, BM25, búsqueda híbrida y reranker
  llm/          cliente único del LLM (LiteLLM + Groq, con respaldo y reintentos)
  agent/        agente LangGraph: SQL seguro, citas y verificación
  api/          API REST (FastAPI)
  mcp_server/   servidor MCP
  evaluation/   conjunto de evaluación y evaluaciones de búsqueda y de respuestas
app/            interfaz Streamlit
docs/decisions/ por qué se eligió cada herramienta o fuente
eval/           conjunto de evaluación e informes generados (eval/reports/)
tests/          tests automáticos (pytest)
data/           datos descargados e índices (no se suben a git)
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

## Fase 5 — Búsqueda híbrida y su evaluación

**Objetivo:** encontrar el documento correcto, y **medirlo** en vez de fiarse de ejemplos sueltos.

```
pregunta ─┬─► Qdrant (significado)  50 candidatos ─┐
          └─► BM25 (palabras exactas) 50 candidatos ─┴─► RRF ─► reranker (20 mejores) ─► top k
```

- **BM25:** puntúa por palabras compartidas, dando más peso a las raras («relatlimab»,
  «mk-3475»). Gana justo donde fallan los embeddings: nombres propios y códigos.
- **RRF (Reciprocal Rank Fusion):** une las dos listas sumando 1/(60 + posición). Usa
  posiciones y no puntuaciones, porque un coseno y una puntuación BM25 no son comparables.
- **Reranker (cross-encoder MedCPT):** lee pregunta y texto *juntos*, así que es más preciso
  que comparar dos vectores calculados por separado, pero lento (~90 ms por texto en una GTX
  1650). Por eso solo reordena los 20 mejores: reordenar 100 tardaba 9 s y 20 tarda ~2 s.

**Conjunto de evaluación** (`eval/golden_set.jsonl`, 102 preguntas): se eligieron 42 trozos
al azar (ensayos, artículos y fichas) y un LLM escribió una pregunta que cada uno responde; ese
documento es la respuesta correcta. Variantes: la misma pregunta **en español** (42) y con el
**código** del fármaco en vez del nombre (18, p. ej. MK-3475 por pembrolizumab).

| Configuración | Recall@1 | Recall@5 | MRR@10 | s/pregunta |
|---|---|---|---|---|
| BM25 (palabras) | 0,54 | 0,72 | 0,63 | 0,1 |
| Denso MiniLM | 0,62 | 0,81 | 0,70 | 0,02 |
| Denso MedCPT | 0,27 | 0,50 | 0,37 | 0,03 |
| Híbrido MiniLM | 0,65 | 0,84 | 0,73 | 0,1 |
| Híbrido MedCPT + reranker | 0,72 | 0,81 | 0,76 | 2,2 |
| **Híbrido MiniLM + reranker** (elegido) | **0,75** | **0,87** | **0,80** | 2,1 |

*Recall@5: % de preguntas cuyo documento correcto sale entre los 5 primeros. MRR: premia que
salga arriba (1 si es el 1.º, 0,5 si es el 2.º...).* Informe completo en `eval/reports/`.

Lo que enseña:

- **El híbrido gana** a cada método por separado, y el reranker suma otros 10 puntos de Recall@1.
- **MedCPT, el modelo biomédico, buscó peor que el general.** Se entrenó con búsquedas cortas
  de PubMed y artículos; aquí las preguntas son frases largas y un tercio de los documentos son
  ensayos y fichas. Como *reranker*, en cambio, sí aporta. Se descartó como buscador por datos,
  no por intuición.
- **Español:** 74 % frente a 98 % en inglés, porque los modelos son de inglés. Por eso el agente
  traduce la pregunta antes de buscar.
- **Limitaciones:** las preguntas son sintéticas y comparten palabras con su documento (BM25
  acierta el 98 % de las parafraseadas), y solo hay una respuesta correcta por pregunta (otro
  documento igual de válido cuenta como fallo). Conviene revisarlas a mano.

## Fases 6 y 7 — Agente que responde citando

**Objetivo:** responder en lenguaje natural sin inventar, y que cada afirmación se pueda comprobar.

```
plan ──► SQL? ──► búsqueda? ──► redactar ──► verificar ──► respuesta
                                    ▲             │
                                    └─────────────┘ (reintento si algo no cuadra)
```

1. **Planificar:** el LLM clasifica la pregunta: datos exactos → SQL; contenido → búsqueda;
   ambas → las dos. También traduce la pregunta al inglés y extrae filtros (fármaco, fase,
   tipo de fuente), traduciendo marcas y códigos a su nombre genérico (Keytruda → pembrolizumab).
2. **SQL seguro:** el LLM escribe la consulta y antes de ejecutarla `sqlglot` comprueba que sea
   una sola sentencia, solo `SELECT` y solo sobre tablas conocidas. Se ejecuta en una transacción
   de **solo lectura**, con 5 s de tiempo máximo y 50 filas como mucho. Si falla, el error se le
   devuelve al LLM para que lo corrija; si devuelve 0 filas, se le pide que revise la lógica.
3. **Redactar:** el LLM solo ve las fuentes numeradas `[S1]...[Sn]` y el resultado `[SQL]`, y
   debe citar cada afirmación.
4. **Verificar:** se comprueba que no cite fuentes inexistentes, que las frases tengan cita y que
   **cada número de la respuesta aparezca en las fuentes**. Si algo falla, reescribe la respuesta
   indicándole qué número o frase no tiene respaldo.

Tres fallos reales que motivaron estas defensas:

- **Totales inventados:** el agente dijo «13 ensayos» de fase 3 con inhibidores de BRAF; eran 18
  (y las filas sumaban 20, porque un ensayo puede usar dos fármacos). Pedírselo en el prompt no
  bastó; la verificación de números sí lo corrige.
- **Un «no existe» falso:** un SQL mal planteado devolvió 0 ensayos BRAF + MEK reclutando y el
  agente lo afirmó con seguridad; había 11. Ahora un resultado vacío se revisa antes de aceptarlo.
- **Citas con otros corchetes:** el modelo a veces escribe `【S1】`; se normalizan para verificarlas.

## Fase 8 — API REST y servidor MCP

**API REST (FastAPI)**, con documentación interactiva en `http://localhost:8000/docs`:

| Endpoint | Qué hace |
|---|---|
| `GET /health` | Estado de Postgres y Qdrant |
| `POST /search` | Búsqueda híbrida con filtros (fuente, fármaco, fase) |
| `POST /ask` | Pregunta al agente: respuesta, fuentes citadas, SQL usado y verificación |
| `GET /trials` | Ensayos filtrados por fármaco, mecanismo, fase, estado, patrocinador |
| `GET /drugs`, `GET /drugs/{nombre}` | Perfil de un fármaco (acepta marca o código: `/drugs/Keytruda`) |
| `GET /landscape` | Panorama competitivo: ensayos por fármaco, fase, año y patrocinador |

Las consultas fijas usan parámetros (`:drug`) en vez de pegar texto en el SQL, para evitar la
inyección SQL.

**Servidor MCP:** las mismas capacidades como herramientas para agentes de IA. La diferencia:
una API REST la usa un programa que ya sabe qué llamar; MCP permite que un agente (Claude,
por ejemplo) **descubra** las herramientas y decida cuándo usarlas. Probado con un cliente MCP
real por stdio.

## Fase 9 — Interfaz (Streamlit)

Cuatro pestañas, que consumen la API (la interfaz no toca la base de datos):

- **Asistente:** chat con la respuesta, un indicador de verificación (✅ citas verificadas o
  ⚠️ qué revisar), el SQL usado y tarjetas con las fuentes citadas y su enlace.
- **Panorama competitivo:** ensayos activos por fármaco, mapa fármaco × fase, ensayos iniciados
  por año y mecanismo, y principales patrocinadores (Pierre Fabre aparece con 6 ensayos). La
  paleta de colores se validó para daltonismo; cada gráfico tiene etiquetas y una vista en tabla.
- **Perfil de fármaco:** fases, estados, patrocinadores, artículos más citados y fichas FDA.
- **Búsqueda:** búsqueda híbrida con filtros.

Un error encontrado al revisar la interfaz: la cifra principal sumaba ensayos por fármaco
(1 422) en lugar de contar ensayos distintos (972). Ahora los totales se calculan en SQL.

## Fase 10 — Evaluación de las respuestas y PDFs de congresos

**Evaluación del agente** (`make eval-generation`): 12 preguntas escritas a mano (4 de datos,
6 de contenido, 2 mixtas). Para las de datos, la respuesta correcta se calculó con SQL escrito
a mano. La fidelidad la puntúa un LLM juez, que descompone la respuesta en afirmaciones y
comprueba cuáles están en las fuentes.

| Métrica | Resultado |
|---|---|
| Ruta correcta (SQL / búsqueda / ambas) | 12 de 12 |
| Respuestas con al menos una cita | 12 de 12 |
| Sin citas a fuentes inexistentes | 12 de 12 |
| Sin números sin respaldo | 11 de 12 (el fallo era del verificador, ver abajo) |
| Dato correcto en preguntas con respuesta conocida | 4 de 4 |
| Fidelidad media (LLM juez) | 84 % |
| Pertinencia media (LLM juez, 1-5) | 4,7 |
| Tiempo medio por respuesta | 3,6 s |

Las tres respuestas con fidelidad baja, revisadas a mano:

- **COLUMBUS (0,33): fallo de búsqueda.** Recuperó COLUMBUS-AD (otro ensayo, adyuvante) en lugar
  de los artículos de resultados, y el agente respondió con honestidad que no tenía datos de
  supervivencia. El juez penalizó esa frase de «no lo sé», que era correcta.
- **Dosis de dabrafenib (0,5): error real no detectado.** La búsqueda no trajo la sección de dosis
  inicial, y las reducciones que dio (1,5 mg, 1 mg) son las de **trametinib**, que aparecen en la
  misma ficha de la combinación. Ni el juez ni la verificación lo detectaron: un número puede
  estar en la fuente y aun así referirse a otro fármaco. Además, el verificador marcó «1,5» como
  sin respaldo porque la fuente escribe «1.5»; ese fallo del verificador ya está corregido.
- **Ensayos activos con relatlimab (0,29): los 7 ensayos son correctos** (comprobado con SQL); el
  juez marcó los títulos como no respaldados, probablemente porque solo ve los primeros 9 000
  caracteres de las fuentes.

Conclusión: el agente no inventa fuentes ni cifras, y dice cuando no sabe; sus fallos vienen
sobre todo de **la búsqueda** (trae el documento equivocado) y de atribuir un dato a un fármaco
vecino. El LLM juez es útil como alarma, pero se equivoca en ambos sentidos.

Cuota de Groq: 8 000 tokens por minuto. El evaluador espera 25 s entre preguntas y el cliente
reintenta y cambia a un modelo de respaldo cuando llega al límite.

**PDFs de congresos** (`make pdfs`): cada página se convierte a texto con `pymupdf4llm`, se
trocea y se indexa con su número de página, congreso, año y fármacos detectados, de modo que
la cita puede decir «ESMO 2025, p. 3». Probado de punta a punta con un PDF de ejemplo; la
carpeta está vacía hasta que se añadan los PDFs reales.

## Limitaciones y siguientes pasos

- **Medir el extractor de IA** (fase 2) contra 30-50 abstracts anotados a mano.
- **Revisar el conjunto de evaluación sintético** y añadir preguntas reales de analistas.
- **El juez de fidelidad es el mismo modelo que responde**, así que tiende a ser indulgente;
  lo ideal es un juez distinto y una muestra revisada por una persona.
- **Cuota gratuita de Groq:** 8 000 tokens por minuto. Con varios usuarios a la vez haría falta
  un plan de pago o un modelo local.
- `trial_drugs` incluye fármacos usados como **comparador**, no solo el experimental.
- ChEMBL (más sinónimos y fármacos) y bge-m3 (tercer modelo de embeddings) quedan opcionales.

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
| BM25 | Búsqueda por palabras exactas que da más peso a las palabras raras |
| Búsqueda híbrida | Combinar búsqueda por palabras (BM25) y por significado (embeddings) |
| Reranker (cross-encoder) | Modelo que lee pregunta y texto juntos para reordenar los resultados |
| Recall@k / MRR | % de veces que el resultado correcto sale entre los k primeros / premio por salir arriba |
| Agente | LLM que decide qué herramientas usar (SQL, búsqueda) para responder |
| LangGraph | Librería para definir un agente como un grafo de pasos |
| API REST | Forma estándar de ofrecer funciones por HTTP (`GET /trials`) |
| MCP | Protocolo para que un agente de IA descubra y use herramientas externas |
| LLM como juez | Usar un LLM para puntuar respuestas de otro (útil, pero con sesgos) |

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
