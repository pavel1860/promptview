



from typing import TYPE_CHECKING, Generic, Type, TypeVar, Callable, List, Any
from promptview.model2.base_namespace import QuerySet
from qdrant_client.http.models import ScoredPoint
from promptview.model2.qdrant.connection import QdrantConnectionManager

if TYPE_CHECKING:
    from promptview.model2.model import Model

MODEL = TypeVar("MODEL", bound="Model")

class QdrantQuerySet(QuerySet[MODEL], Generic[MODEL]):
    def __init__(self, model_class: Type[MODEL]):
        super().__init__(model_class)
        self._filters: dict[str, Any] = {}
        self._limit: int | None = None
        self._query: str | None = None

    def filter(self, filter_fn: Callable[[MODEL], bool] = None, **kwargs) -> "QdrantQuerySet[MODEL]":
        self._filters.update(kwargs)
        return self

    def limit(self, limit: int) -> "QdrantQuerySet[MODEL]":
        self._limit = limit
        return self
    
    
    def similar(self, query: str) -> "QdrantQuerySet[MODEL]":
        self._query = query
        return self

    async def execute(self) -> List[MODEL]:
        ns = self.model_class.get_namespace()
        collection_name = ns.name
        if self._query:
            vectors = await ns.batch_vectorizer.embed_query(self._query)
            
        # This example assumes a simple key-value filtering with no payload transformation yet
        # results = await QdrantConnectionManager.simple_query(
        #     collection_name=collection_name,
        #     filters=self._filters,
        #     limit=self._limit
        # )
        results = await QdrantConnectionManager.execute_query(
            collection_name=collection_name,
            query=vectors,
            limit=self._limit
        )
        primary_key = ns.primary_key.name
        def unpack_point(point: ScoredPoint) -> dict[str, Any]:
            meta = point.payload or {}
            return meta | {
                "score": point.score,
                "vector": point.vector,
            } | {primary_key: point.id}
        
        return [ns.instantiate_model(unpack_point(hit)) for hit in results]
