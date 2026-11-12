from qdrant_client import QdrantClient
from sqlalchemy import create_engine, text

from onco_research_ai.config import settings


def check_postgres() -> None:
    engine = create_engine(settings.postgres_url)
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar()
    print("Postgres OK:", version)


def check_qdrant() -> None:
    client = QdrantClient(url=settings.qdrant_url)
    print("Qdrant OK, colecciones:", client.get_collections())


if __name__ == "__main__":
    check_postgres()
    check_qdrant()