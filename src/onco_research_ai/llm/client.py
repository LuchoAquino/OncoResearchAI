"""Un único punto de acceso al LLM para todo el proyecto (vía LiteLLM).

LiteLLM traduce la misma llamada a cualquier proveedor (Groq, Gemini, OpenAI, Ollama...):
cambiar de modelo es cambiar un texto, no el código. Si el modelo principal falla (límite de
cuota, caída), se prueban los de respaldo en orden.
"""

import logging

import litellm
from pydantic import BaseModel
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from onco_research_ai.config import settings

litellm.suppress_debug_info = True
litellm.drop_params = True  # ignora parámetros que un modelo de respaldo no admita
logging.getLogger("LiteLLM").setLevel(logging.ERROR)


class _DropLiteLLMWorkerNoise(logging.Filter):
    """LiteLLM deja tareas de registro internas pendientes al usarlo de forma síncrona; asyncio
    las reporta como error aunque son inofensivas. Se descartan SOLO esos mensajes."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "LoggingWorker" not in record.getMessage()


logging.getLogger("asyncio").addFilter(_DropLiteLLMWorkerNoise())

# Cuota gratuita de Groq (medida en las cabeceras x-ratelimit): 8 000 tokens/minuto y
# 1 000 peticiones/día POR MODELO. Una respuesta con fuentes gasta ~3 000 tokens.
MODEL = "groq/openai/gpt-oss-120b"
FALLBACKS = ["groq/openai/gpt-oss-20b", "groq/qwen/qwen3.8-27b"]


@retry(
    # Límite por minuto: esperar y reintentar en vez de fallar (10 s, 20 s, 40 s, 60 s).
    retry=retry_if_exception_type(litellm.RateLimitError),
    wait=wait_exponential(multiplier=10, max=60),
    stop=stop_after_attempt(5),
    before_sleep=before_sleep_log(logging.getLogger(__name__), logging.WARNING),
    reraise=True,
)
def complete(
    messages: list[dict],
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    resp = litellm.completion(
        model=MODEL,
        messages=messages,
        api_key=settings.groq_api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort="low",
        response_format={"type": "json_object"} if json_mode else None,
        num_retries=1,
        fallbacks=FALLBACKS,
    )
    return resp.choices[0].message.content or ""


def complete_json[T: BaseModel](messages: list[dict], schema: type[T], **kw) -> T:
    """Pide JSON y lo valida con Pydantic: si el modelo devuelve otra cosa, falla aquí."""
    return schema.model_validate_json(complete(messages, json_mode=True, **kw))
