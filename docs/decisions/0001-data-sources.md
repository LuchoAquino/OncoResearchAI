# ADR 0001 — Fuentes de datos

- **Estado:** aceptada
- **Fecha:** 2026-11-12
- **Fase del plan:** 0 (exploración de fuentes)

## Contexto

El proyecto replica el caso de uso de una oferta de prácticas en veille concurrentielle
oncológica: alinear datos estructurados y no estructurados de fuentes heterogéneas, para
responder preguntas sobre el panorama competitivo de **melanoma**.

Restricciones: solo datos abiertos, sin pago, y un alcance pequeño para poder entender y
explicar cada paso. Criterio de elección: **las fuentes más simples de implementar y más
importantes** para el caso de uso.

## Decisión

Cuatro APIs públicas y una carga manual de PDFs:

| # | Fuente | Rol | Tipo de dato |
|---|---|---|---|
| 1 | ClinicalTrials.gov API v2 | Ensayos clínicos (fase, estado, sponsor, intervenciones) | Estructurado + texto |
| 2 | Europe PMC REST | Literatura científica (abstracts) | No estructurado |
| 3 | openFDA `/drug/label` | Fichas técnicas de fármacos aprobados | Semi-estructurado |
| 4 | ChEMBL | Diccionario de sinónimos y mecanismos de acción | Estructurado (referencia) |
| 5 | PDFs manuales (congresos) | Datos recientes aún no publicados | No estructurado |

ChEMBL no aporta documentos para consultar: es el **pegamento** que permite reconocer que
ensayos, artículos y fichas hablan del mismo fármaco.

## Alternativas descartadas

- **PubMed (E-utilities):** Europe PMC ya lo indexa; usar ambos duplicaría artículos.
- **Open Targets, EMA, FAERS:** útiles, pero añaden complejidad sin ser imprescindibles
  para el MVP. Se pueden incorporar luego reutilizando el patrón de los conectores.

## Hallazgos del smoke test (2026-11-12)

Consultas reales a las cuatro APIs, sin claves de acceso:

| Fuente | Resultado | Paginación |
|---|---|---|
| ClinicalTrials.gov | 3 782 ensayos con condición «melanoma» | `pageToken` (token opaco) |
| Europe PMC | 3 532 artículos con `melanoma AND (encorafenib OR binimetinib) AND HAS_ABSTRACT:y` | `cursorMark` |
| openFDA | 48 fichas con «melanoma» en la indicación | offset: `skip` + `limit` |
| ChEMBL | 5 fármacos resueltos con sinónimos y mecanismo; 7 561 mecanismos en total | `page_meta` (offset + `next`) |

### Riesgos de calidad detectados

1. **Ruido en la búsqueda por palabra clave.** ClinicalTrials.gov devolvió un ensayo de
   «non-melanoma skin cancer» y uno de melanoma uveal (un subtipo distinto) entre los
   primeros resultados. Europe PMC devolvió un artículo sobre cáncer de pulmón.
   → La fase 2 debe medir y filtrar este ruido.
2. **Campos opcionales y de distinto tipo.** `phases` es una *lista* y puede ser `None`
   (estudios observacionales) o `['NA']` (no aplica). → El esquema debe tolerarlo.
3. **Fichas openFDA sin bloque `openfda`.** 3 de 10 fichas inspeccionadas no traen nombre
   normalizado del fármaco (algunas son antiguas, p. ej. 2014). → No se pueden identificar
   por ese campo.
4. **Versionado en openFDA.** Una ficha tiene identidad (`set_id`) y varias versiones.
   → Hay que decidir cuál conservar.
5. **Sinónimos con ruido en ChEMBL.** Aparecen combinaciones como «Pembrolizumab component
   of mk-1308a». → Filtrar antes de usarlos para alinear.
6. **ChEMBL devuelve errores 500 intermitentes.** → Los conectores deben reintentar con
   espera exponencial (`tenacity`), solo ante errores transitorios (5xx, 429, red), nunca
   ante 4xx.

## Consecuencias

- Los conectores de la fase 1 comparten un patrón: petición con *timeout*, reintentos
  selectivos, paginación hasta agotar resultados y guardado de la respuesta **cruda** en
  `data/raw/` antes de transformar nada.
- Cada fuente aporta una clave de unión (`NCT…`, `PMID`/`DOI`, `set_id`, `CHEMBL…`); el
  modelo de datos de la fase 2 se construye alrededor de esas claves.
- Las cifras de arriba son una fotografía de esa fecha, no un valor fijo: las fuentes se
  actualizan continuamente.
