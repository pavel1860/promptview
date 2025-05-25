from typing import Any, List
from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, SearchParams
import os

class QdrantConnectionManager:
    _client: AsyncQdrantClient | None = None

    @classmethod
    def get_client(cls) -> AsyncQdrantClient:
        if cls._client is None:
            cls._client = AsyncQdrantClient(
                host=os.getenv("QDRANT_HOST", "localhost"),
                port=int(os.getenv("QDRANT_PORT", "6333"))
            )
        return cls._client

    @classmethod
    async def simple_query(
        cls,
        collection_name: str,
        filters: dict[str, Any],
        limit: int | None = None,
    ) -> List[dict]:
        """
        Basic retrieval based on payload field matches.
        No vector similarity for now.
        """
        client = cls.get_client()

        conditions = [
            FieldCondition(key=key, match=MatchValue(value=value))
            for key, value in filters.items()
        ]

        qdrant_filter = Filter(must=conditions) if conditions else None

        hits = await client.scroll(
            collection_name=collection_name,
            scroll_filter=qdrant_filter,
            limit=limit or 10,
            with_payload=True,
            with_vectors=False
        )

        return [point.payload for point in hits[0]]
