from typing import Any, Optional, Type, List
from typing_extensions import TypeVar
from promptview.model2.base_namespace import Namespace, NSFieldInfo, QuerySet, QuerySetSingleAdapter
from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.qdrant.field_info import QdrantFieldInfo
from promptview.model2.qdrant.query_set import QdrantQuerySet  # Placeholder for later
from promptview.model2.qdrant.connection import QdrantConnectionManager  # Placeholder for later
from promptview.model2.model import Model
from qdrant_client.models import PointStruct
import uuid

MODEL = TypeVar("MODEL", bound="Model")

class QdrantNamespace(Namespace[MODEL, QdrantFieldInfo]):
    """Qdrant implementation of Namespace"""
    
    def __init__(
        self,
        name: str,
        is_versioned: bool = False,
        is_repo: bool = False,
        is_context: bool = False,
        is_artifact: bool = False,
        repo_namespace: Optional[str] = None,
        namespace_manager: Optional["NamespaceManager"] = None
    ):
        super().__init__(
            name=name,
            db_type="qdrant",
            is_versioned=is_versioned,
            is_repo=is_repo,
            is_context=is_context,
            is_artifact=is_artifact,
            repo_namespace=repo_namespace,
            namespace_manager=namespace_manager
        )
        
    def add_field(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ) -> QdrantFieldInfo:
        """
        Add a field to the Qdrant namespace.
        """
        field = QdrantFieldInfo(
            name=name,
            field_type=field_type,
            extra=extra,
        )

        if field.is_primary_key:
            if self.find_primary_key() is not None:
                raise ValueError(f"Primary key field already exists, cannot add: {name}")
            self._primary_key = field

        if field.is_default_temporal:
            if self.default_temporal_field is not None:
                raise ValueError(f"Default temporal field already set: {self.default_temporal_field.name}")
            self.default_temporal_field = field

        if field.is_vector:
            self._vector_fields[name] = field

        self._fields[name] = field
        return field


    async def create_namespace(self):
        """Create Qdrant collection (vector index)"""
        # Will use QdrantConnectionManager later
        raise NotImplementedError("create_namespace not implemented yet")

    async def drop_namespace(self):
        """Drop Qdrant collection"""
        raise NotImplementedError("drop_namespace not implemented yet")

    async def save(self, model: MODEL) -> MODEL:
        namespace = self
        client = QdrantConnectionManager.get_client()
        collection_name = namespace.name

        dump = model.model_dump()
        dump = namespace.validate_model_fields(dump)

        vector_payload = {}
        if namespace.need_to_transform:
            vector_payload = await namespace.transform_model(model)
            dump.update(vector_payload)

        point_id = dump.get(namespace.primary_key.name)
        if point_id is None:
            point_id = str(uuid.uuid4())
            dump[namespace.primary_key.name] = point_id

        if not vector_payload:
            raise ValueError("Missing vector payload: cannot save Qdrant point without embedding")

        vector_field = next(iter(vector_payload.keys()))
        vector = vector_payload[vector_field]

        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=dump
        )

        await client.upsert(
            collection_name=collection_name,
            points=[point]
        )

        return namespace.instantiate_model(dump)


    async def get(self, id: Any) -> MODEL | None:
        client = QdrantConnectionManager.get_client()
        collection_name = self.name

        result = await client.retrieve(
            collection_name=collection_name,
            ids=[id],
            with_payload=True,
            with_vectors=False
        )

        if not result:
            return None

        payload = result[0].payload
        return self.instantiate_model(payload)


    async def delete(self, id: Any) -> MODEL | None:
        client = QdrantConnectionManager.get_client()
        collection_name = self.name

        existing = await self.get(id)
        if not existing:
            return None

        await client.delete(
            collection_name=collection_name,
            points_selector={"points": [id]}
        )
        return existing


    def query(self, **kwargs) -> QuerySet:
        """Return a QdrantQuerySet"""
        return QdrantQuerySet(self.model_class)
