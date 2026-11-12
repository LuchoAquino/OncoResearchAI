import logging


def setup_logging(level: int = logging.INFO) -> None:
    """Configura el logging una sola vez, al arrancar el programa (no en cada módulo)."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    # httpx registra cada petición a nivel INFO; con cientos de páginas es ruido
    logging.getLogger("httpx").setLevel(logging.WARNING)
