



from typing import Generic, Type, TypeVar, Callable, List, Any
from promptview.model2.base_namespace import QuerySet
from promptview.model2.model import Model
from promptview.model2.qdrant.connection import QdrantConnectionManager

MODEL = TypeVar("MODEL", bound="Model")

class QdrantQuerySet(QuerySet[MODEL], Generic[MODEL]):
    def __init__(self, model_class: Type[MODEL]):
        super().__init__(model_class)
        self._filters: dict[str, Any] = {}
        self._limit: int | None = None

    def filter(self, filter_fn: Callable[[MODEL], bool] = None, **kwargs) -> "QdrantQuerySet[MODEL]":
        self._filters.update(kwargs)
        return self

    def limit(self, limit: int) -> "QdrantQuerySet[MODEL]":
        self._limit = limit
        return self

    async def execute(self) -> List[MODEL]:
        namespace = self.model_class.get_namespace()
        collection_name = namespace.name

        # This example assumes a simple key-value filtering with no payload transformation yet
        results = await QdrantConnectionManager.simple_query(
            collection_name=collection_name,
            filters=self._filters,
            limit=self._limit
        )

        return [namespace.instantiate_model(hit) for hit in results]
