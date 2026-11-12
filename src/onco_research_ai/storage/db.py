from sqlalchemy import Engine, create_engine

from onco_research_ai.config import settings
from onco_research_ai.storage.models import Base


def get_engine() -> Engine:
    return create_engine(settings.postgres_url)


def init_db(engine: Engine | None = None) -> None:
    """Crea las tablas que no existan. No modifica tablas existentes (para eso: migraciones)."""
    Base.metadata.create_all(engine or get_engine())
