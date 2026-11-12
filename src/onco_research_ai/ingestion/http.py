"""Capa HTTP común a todos los conectores: timeout, cabecera y reintentos."""

import logging

import httpx
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def make_client(
    timeout: float = 30.0, transport: httpx.BaseTransport | None = None
) -> httpx.Client:
    """Un cliente reutilizable: mantiene la conexión abierta entre peticiones (más rápido).

    `transport` permite inyectar un servidor falso en los tests.
    """
    return httpx.Client(
        timeout=timeout,
        headers={"User-Agent": "OncoResearchAI/0.1 (portfolio project)"},
        transport=transport,
    )


def is_retryable(exc: BaseException) -> bool:
    """Reintentar solo fallos TRANSITORIOS: 5xx, 429 y errores de red.

    Un 400 o 404 es culpa nuestra: reintentar no lo arreglaría.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status == 429
    return isinstance(exc, httpx.TransportError)


@retry(
    retry=retry_if_exception(is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, max=20),  # 1 s, 2 s, 4 s, 8 s...
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,  # si se agotan los intentos, lanza el error original
)
def get_json(client: httpx.Client, url: str, params: dict | None = None) -> dict:
    response = client.get(url, params=params)
    response.raise_for_status()
    return response.json()
