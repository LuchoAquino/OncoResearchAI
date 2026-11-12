"""Un único punto de acceso al LLM para todo el proyecto (vía LiteLLM).

LiteLLM traduce la misma llamada a cualquier proveedor (Groq, Gemini, OpenAI, Ollama...):
cambiar de modelo es cambiar un texto, no el código. Si el modelo principal falla (límite de
cuota, caída), se prueban los de respaldo en orden.
"""

import logging

import litellm
from pydantic import BaseModel

from onco_research_ai.config import settings

litellm.suppress_debug_info = True
litellm.drop_params = True  # ignora parámetros que un modelo de respaldo no admita
logging.getLogger("LiteLLM").setLevel(logging.WARNING)

MODEL = "groq/openai/gpt-oss-120b"
FALLBACKS = ["groq/openai/gpt-oss-20b", "groq/qwen/qwen3.8-27b"]


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
        num_retries=3,
        fallbacks=FALLBACKS,
    )
    return resp.choices[0].message.content or ""


def complete_json[T: BaseModel](messages: list[dict], schema: type[T], **kw) -> T:
    """Pide JSON y lo valida con Pydantic: si el modelo devuelve otra cosa, falla aquí."""
    return schema.model_validate_json(complete(messages, json_mode=True, **kw))
