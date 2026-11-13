"""Cuánto se ha usado cada modelo. Se guarda en data/llm_usage.json (no se sube a git).

Qué se sabe de verdad, por proveedor:
- Esta aplicación: cuenta SUS propias llamadas y tokens de hoy, para todos los modelos.
- Groq: además informa, en cada respuesta, de las peticiones que le quedan hoy y de los tokens
  por minuto; y, cuando se agota el límite diario de tokens, el aviso de error dice límite y gasto.
- Gemini: la API no informa de la cuota restante; solo se ve en Google AI Studio. Si se
  configura GEMINI_DAILY_REQUEST_LIMIT, se calcula lo que queda a partir de lo contado aquí
  (no incluye lo que se gaste con la misma clave fuera de esta aplicación).
- Ollama (local): sin límite.
"""

import json
import re
import threading
import time
from datetime import date
from pathlib import Path

PATH = Path("data/llm_usage.json")
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"days": {}, "provider": {}}


def _save(data: dict) -> None:
    # Se conservan solo los últimos 8 días.
    data["days"] = dict(sorted(data["days"].items())[-8:])
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    tmp.replace(PATH)


def record(model_key: str, tokens: int = 0, headers: dict | None = None) -> None:
    """Anota una llamada correcta y, si el proveedor dio cabeceras de límite, las guarda."""
    with _lock:
        data = _load()
        day = data["days"].setdefault(date.today().isoformat(), {})
        slot = day.setdefault(model_key, {"requests": 0, "tokens": 0})
        slot["requests"] += 1
        slot["tokens"] += int(tokens or 0)
        info = parse_rate_headers(headers or {})
        if info:
            data["provider"].setdefault(model_key, {}).update(
                {**info, "at": time.time()}
            )
        _save(data)


def record_quota_error(model_key: str, message: str) -> None:
    """Un 429 de Groq por tokens/día dice 'Limit 200000, Used 199336': se guarda."""
    m = re.search(r"Limit (\d+), Used (\d+)", message)
    if not m or "per day" not in message:
        return
    with _lock:
        data = _load()
        data["provider"].setdefault(model_key, {}).update(
            {
                "tokens_day_limit": int(m[1]),
                "tokens_day_used": int(m[2]),
                "at_day_error": time.time(),
            }
        )
        _save(data)


def parse_rate_headers(headers: dict) -> dict:
    """Cabeceras x-ratelimit-* (con o sin el prefijo 'llm_provider-' que añade LiteLLM)."""
    clean = {k.lower().removeprefix("llm_provider-"): v for k, v in headers.items()}
    out = {}
    for src, dst in (
        ("x-ratelimit-remaining-requests", "remaining_requests"),
        ("x-ratelimit-limit-requests", "limit_requests"),
        ("x-ratelimit-remaining-tokens", "remaining_tokens_minute"),
        ("x-ratelimit-limit-tokens", "limit_tokens_minute"),
    ):
        if src in clean:
            try:
                out[dst] = int(float(clean[src]))
            except (TypeError, ValueError):
                pass
    return out


def summary(model_key: str, daily_request_limit: int = 0) -> dict:
    """Todo lo que se sabe de un modelo, listo para mostrar."""
    with _lock:
        data = _load()
    today = data["days"].get(date.today().isoformat(), {}).get(model_key, {})
    info = dict(data["provider"].get(model_key, {}))
    out = {
        "requests_today": today.get("requests", 0),
        "tokens_today": today.get("tokens", 0),
        "reported": {},
    }
    day = 24 * 3600
    # Lo que informa el proveedor solo vale si es reciente (< 24 h).
    if info.get("at") and time.time() - info["at"] < day:
        for k in (
            "remaining_requests",
            "limit_requests",
            "remaining_tokens_minute",
            "limit_tokens_minute",
        ):
            if k in info:
                out["reported"][k] = info[k]
    if info.get("at_day_error") and time.time() - info["at_day_error"] < day:
        out["reported"]["tokens_day_limit"] = info["tokens_day_limit"]
        out["reported"]["tokens_day_used"] = info["tokens_day_used"]
    if daily_request_limit:
        out["requests_left_estimate"] = max(
            0, daily_request_limit - out["requests_today"]
        )
        out["daily_request_limit"] = daily_request_limit
    return out
