# Atajos para todo el flujo. `make help` lista los comandos.
.PHONY: help up install ingest load quality index index-medcpt bm25 pdfs extract eval-retrieval eval-generation api mcp ui test lint pipeline

help:  ## Lista los comandos
	@grep -E "^[a-z-]+:.*##" $(MAKEFILE_LIST) | awk -F ":.*## " '{printf "  make %-16s %s\n", $$1, $$2}'

up:  ## Arranca Postgres y Qdrant (Docker)
	docker compose up -d
install:  ## Instala las dependencias
	uv sync
ingest:  ## Descarga los datos de las APIs a data/raw/
	uv run python -m onco_research_ai.ingestion all
load:  ## Carga, limpia y enlaza los datos en Postgres
	uv run python -m onco_research_ai.storage.load
quality:  ## Informe de calidad de datos (eval/reports/)
	uv run python -m onco_research_ai.quality.checks
index:  ## Indexa los textos en Qdrant con MiniLM (~6 min en GPU) y crea el índice BM25
	uv run python -m onco_research_ai.retrieval.index --model minilm
	uv run python -m onco_research_ai.retrieval.bm25
index-medcpt:  ## Indexa también con MedCPT (~35 min en GPU; solo para comparar)
	uv run python -m onco_research_ai.retrieval.index --model medcpt
pdfs:  ## Indexa los PDFs de congresos de data/manual_pdfs/
	uv run python -m onco_research_ai.ingestion.manual_pdfs
extract:  ## Extractor LLM sobre 20 artículos más (usa cuota de Groq)
	uv run python -m onco_research_ai.processing.extractor --limit 20
eval-retrieval:  ## Compara configuraciones de búsqueda (necesita index-medcpt)
	uv run python -m onco_research_ai.evaluation.retrieval_eval
eval-generation:  ## Evalúa las respuestas del agente (~12 min por la cuota de Groq)
	uv run python -m onco_research_ai.evaluation.generation_eval
api:  ## API REST en http://localhost:8000/docs
	uv run uvicorn onco_research_ai.api.main:app --port 8000
mcp:  ## Servidor MCP por stdio (para Claude Desktop / Claude Code)
	uv run python -m onco_research_ai.mcp_server.server
ui:  ## Interfaz Streamlit en http://localhost:8501 (con la API corriendo)
	uv run streamlit run app/streamlit_app.py
test:  ## Tests
	uv run pytest -q
lint:  ## Estilo y errores comunes
	uv run ruff check . && uv run ruff format --check .
pipeline: up ingest load quality index  ## Todo el flujo de datos de principio a fin
