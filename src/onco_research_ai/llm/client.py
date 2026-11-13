"""Un único punto de acceso al LLM para todo el proyecto (vía LiteLLM), con varios modelos.

LiteLLM traduce la misma llamada a cualquier proveedor: cambiar de modelo es cambiar un texto.
La interfaz elige el modelo de cada pregunta; el resto del código (agente, SQL, extractor) llama
a `complete()` sin saber cuál es, porque la elección viaja en una variable de contexto.

Si el modelo elegido se queda sin cuota, se prueba el siguiente disponible y la respuesta
dice quién contestó de verdad: un modelo de respaldo más pequeño puede responder peor y eso no
debe pasar en silencio.
"""

import contextlib
import contextvars
import logging
import re
import time
from dataclasses import dataclass, field

import httpx
import litellm
from pydantic import BaseModel

from onco_research_ai.config import settings
from onco_research_ai.llm import usage

litellm.suppress_debug_info = True
litellm.drop_params = True  # ignora parámetros que un modelo no admita
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


class _DropLiteLLMWorkerNoise(logging.Filter):
    """LiteLLM deja tareas de registro internas pendientes al usarlo de forma síncrona; asyncio
    las reporta como error aunque son inofensivas. Se descartan SOLO esos mensajes."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "LoggingWorker" not in record.getMessage()


logging.getLogger("asyncio").addFilter(_DropLiteLLMWorkerNoise())


@dataclass(frozen=True)
class ModelSpec:
    key: str
    label: str
    provider: str  # groq | gemini | ollama
    litellm_model: str
    note: str  # una línea sobre su cuota, para la interfaz
    extra: dict = field(default_factory=dict)


# Los tres modelos que se pueden elegir. Para cambiar uno basta con editar esta tabla.
MODELS: dict[str, ModelSpec] = {
    "groq": ModelSpec(
        "groq",
        "Groq · gpt-oss-120b",
        "groq",
        "groq/openai/gpt-oss-120b",
        "Free tier: 8,000 tokens/min, 200,000 tokens/day, 1,000 requests/day.",
        {"reasoning_effort": "low"},
    ),
    "gemini": ModelSpec(
        "gemini",
        "Google · Gemini 3.1 Flash-Lite",
        "gemini",
        "gemini/gemini-3.1-flash-lite",
        "Free tier. The remaining quota is only shown in Google AI Studio.",
    ),
    "local": ModelSpec(
        "local",
        "Local · Ollama (this computer)",
        "ollama",
        "ollama_chat/qwen3:4b-instruct-2507-q4_K_M",
        "No limit and nothing leaves your computer. Small model: weaker, and slower.",
    ),
}
DEFAULT_MODEL = "groq"
OLLAMA_URL = "http://localhost:11434"

# Modelo elegido y llamadas hechas en la pregunta actual (viajan con el contexto de ejecución).
_selected: contextvars.ContextVar[str] = contextvars.ContextVar(
    "llm_selected", default=DEFAULT_MODEL
)
_calls: contextvars.ContextVar[list | None] = contextvars.ContextVar(
    "llm_calls", default=None
)


class NoModelAvailable(RuntimeError):
    pass


def availability(key: str) -> tuple[bool, str]:
    """¿Se puede usar este modelo ahora? y, si no, por qué."""
    spec = MODELS[key]
    if spec.provider == "groq":
        return (
            (True, "")
            if settings.groq_api_key
            else (False, "GROQ_API_KEY is missing in .env")
        )
    if spec.provider == "gemini":
        return (
            (True, "")
            if settings.gemini_api_key
            else (False, "GEMINI_API_KEY is missing in .env")
        )
    name = spec.litellm_model.split("/", 1)[1]
    try:
        tags = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=2).json().get("models", [])
    except Exception:  # noqa: BLE001
        return False, "Ollama is not running (start it with `ollama serve`)"
    have = {m["name"] for m in tags}
    if name in have or f"{name}:latest" in have:
        return True, ""
    return False, f"Model not downloaded (run `ollama pull {name}`)"


@contextlib.contextmanager
def use_model(key: str | None):
    """Dentro del bloque, todas las llamadas usan `key`; entrega la lista de llamadas hechas."""
    key = key if key in MODELS else DEFAULT_MODEL
    calls: list = []
    t1, t2 = _selected.set(key), _calls.set(calls)
    try:
        yield calls
    finally:
        _selected.reset(t1)
        _calls.reset(t2)


def _chain() -> list[str]:
    first = _selected.get()
    return [first] + [k for k in MODELS if k != first]


def _kwargs(spec: ModelSpec, messages, json_mode, temperature, max_tokens) -> dict:
    kw = {
        "model": spec.litellm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "num_retries": 0,
        "timeout": 180,
        **spec.extra,
    }
    if json_mode:
        kw["response_format"] = {"type": "json_object"}
    if spec.provider == "groq":
        kw["api_key"] = settings.groq_api_key
    elif spec.provider == "gemini":
        kw["api_key"] = settings.gemini_api_key
    else:
        kw["api_base"] = OLLAMA_URL
    return kw


def _is_daily_quota(message: str) -> bool:
    return bool(
        re.search(r"per day|PerDay|daily|TPD|RPD|quota", message, re.IGNORECASE)
    ) and not re.search(r"per minute|PerMinute", message, re.IGNORECASE)


def complete(
    messages: list[dict],
    json_mode: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 2048,
) -> str:
    errors = []
    for key in _chain():
        ok, why = availability(key)
        if not ok:
            errors.append(f"{key}: {why}")
            continue
        spec = MODELS[key]
        for attempt in range(2):  # un reintento tras esperar si el límite es por minuto
            try:
                resp = litellm.completion(
                    **_kwargs(spec, messages, json_mode, temperature, max_tokens)
                )
            except litellm.RateLimitError as exc:
                msg = str(exc)
                usage.record_quota_error(key, msg)
                if attempt == 0 and not _is_daily_quota(msg):
                    logger.warning("%s: límite por minuto, espero 20 s", key)
                    time.sleep(20)
                    continue
                errors.append(f"{key}: quota exhausted")
                break
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{key}: {exc.__class__.__name__}")
                logger.warning("%s falló: %s", key, str(exc)[:160])
                break
            hidden = getattr(resp, "_hidden_params", {}) or {}
            total = getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0
            usage.record(key, total, hidden.get("additional_headers"))
            if (calls := _calls.get()) is not None:
                calls.append(key)
            return resp.choices[0].message.content or ""
    raise NoModelAvailable("No model could answer: " + "; ".join(errors))


def extract_json(text: str) -> str:
    """Saca el JSON de la respuesta aunque el modelo lo envuelva en ```json ... ``` o añada texto.

    Los modelos pequeños lo hacen a menudo; un lector estricto rechazaría respuestas válidas.
    """
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def complete_json[T: BaseModel](messages: list[dict], schema: type[T], **kw) -> T:
    """Pide JSON y lo valida con Pydantic: si el modelo devuelve otra cosa, falla aquí."""
    return schema.model_validate_json(
        extract_json(complete(messages, json_mode=True, **kw))
    )


def models_status() -> list[dict]:
    """Lista para la interfaz: cada modelo, si está disponible y su uso."""
    out = []
    for key, spec in MODELS.items():
        ok, why = availability(key)
        limit = settings.gemini_daily_request_limit if spec.provider == "gemini" else 0
        out.append(
            {
                "key": key,
                "label": spec.label,
                "provider": spec.provider,
                "note": spec.note,
                "available": ok,
                "reason": why,
                "usage": usage.summary(key, limit),
            }
        )
    return out
