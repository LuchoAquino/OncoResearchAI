"""Acceso a Qdrant: crear colecciones, insertar puntos y buscar con filtros."""

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from onco_research_ai.config import settings

# Campos del payload por los que se podrá filtrar (cada uno recibe un índice).
KEYWORD_FIELDS = ["source", "drugs", "phases", "sponsor_class", "section"]
INTEGER_FIELDS = ["year"]


def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def collection_name(model_key: str) -> str:
    return f"chunks_{model_key.replace('-', '_')}"


def recreate_collection(client: QdrantClient, name: str, dim: int) -> None:
    if client.collection_exists(name):
        client.delete_collection(name)
    # Cosine: la distancia que corresponde a vectores normalizados.
    client.create_collection(
        name, vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
    )
    for f in KEYWORD_FIELDS:
        client.create_payload_index(name, f, PayloadSchemaType.KEYWORD)
    for f in INTEGER_FIELDS:
        client.create_payload_index(name, f, PayloadSchemaType.INTEGER)


def upsert(client: QdrantClient, name: str, ids, vectors, payloads) -> None:
    client.upsert(
        name,
        points=[
            PointStruct(id=i, vector=v.tolist(), payload=p)
            for i, v, p in zip(ids, vectors, payloads, strict=True)
        ],
    )


def search(client: QdrantClient, name: str, vector, k: int = 5, **filters):
    """Los k puntos más cercanos al vector, opcionalmente restringidos por campos del payload."""
    conditions = [
        FieldCondition(key=key, match=MatchValue(value=v))
        for key, v in filters.items()
        if v
    ]
    return client.query_points(
        name,
        query=vector.tolist(),
        limit=k,
        query_filter=Filter(must=conditions) if conditions else None,
        with_payload=True,
    ).points
