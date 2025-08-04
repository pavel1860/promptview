from pydantic import BaseModel, PrivateAttr
from typing import Any, Type, Self

from promptview.model.model_meta import ModelMeta

class Model(BaseModel, metaclass=ModelMeta):
    """Base class for all ORM models."""

    _is_base: bool = True
    _db_type: str = "postgres"
    _namespace_name: str = PrivateAttr(default=None)
    _is_versioned: bool = PrivateAttr(default=False)
    _ctx_token: Any = PrivateAttr(default=None)
    # ...add other ORM-internal attrs as needed...

    @classmethod
    def get_namespace_name(cls) -> str:
        return cls._namespace_name

    @classmethod
    def get_namespace(cls):
        from promptview.model.namespace_manager import NamespaceManager
        return NamespaceManager.get_namespace(cls.get_namespace_name())

    @classmethod
    async def initialize(cls):
        """Create DB table/collection for this model."""
        await cls.get_namespace().create_namespace()

    @classmethod
    async def get(cls: Type[Self], id: Any) -> Self:
        data = await cls.get_namespace().get(id)
        if not data:
            raise ValueError(f"{cls.__name__} with ID '{id}' not found")
        return cls(**data)

    async def save(self, *args, **kwargs) -> Self:
        ns = self.get_namespace()
        dump = self.model_dump()
        result = await ns.insert(dump)
        for key, value in result.items():
            setattr(self, key, value)
        return self

    async def update(self, **kwargs) -> Self:
        ns = self.get_namespace()
        result = await ns.update(self.primary_id, kwargs)
        if result is None:
            raise ValueError(f"{self.__class__.__name__} with ID '{self.primary_id}' not found")
        for key, value in result.items():
            setattr(self, key, value)
        return self

    async def delete(self):
        return await self.get_namespace().delete(self.primary_id)

    @property
    def primary_id(self):
        ns = self.get_namespace()
        return getattr(self, ns.primary_key.name)

    # ... add query(), add(), add_rel(), fetch(), etc. as needed ...
