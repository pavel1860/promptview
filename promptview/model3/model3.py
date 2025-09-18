from pydantic import BaseModel, PrivateAttr
from typing import TYPE_CHECKING, Any, Type, Self, TypeVar, Generic, runtime_checkable, Protocol



from .model_meta import ModelMeta
if TYPE_CHECKING:
    from .postgres2.pg_query_set import PgSelectQuerySet
    from promptview.model3.base.base_namespace import BaseNamespace

MODEL = TypeVar("MODEL", bound="Model")
JUNCTION_MODEL = TypeVar("JUNCTION_MODEL", bound="Model")

@runtime_checkable
class Modelable(Protocol, Generic[MODEL]):
    def to_model(self) -> MODEL:
        ...
        
    @classmethod
    def query(cls) -> "PgSelectQuerySet[MODEL]":
        ...


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
        """Get the namespace name for this model."""
        # In Pydantic's PrivateAttr, the value is stored on the class as a plain attribute
        val = getattr(cls, "_namespace_name", None)
        if isinstance(val, str):
            return val
        raise ValueError(f"Namespace name not set for {cls.__name__}")

    @classmethod
    def get_namespace(cls) -> "BaseNamespace":
        from promptview.model3.namespace_manager2 import NamespaceManager
        return NamespaceManager.get_namespace(cls.get_namespace_name())

    @classmethod
    async def initialize(cls):
        """Create DB table/collection for this model."""
        await cls.get_namespace().create_namespace()
        
    def __enter__(self):
        """Enter the context"""
        ns = self.get_namespace()
        self._ctx_token = ns.set_ctx(self)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        """Exit the context"""
        ns = self.get_namespace()
        ns.set_ctx(None)
        self._ctx_token = None
        
    @classmethod
    def current(cls) -> Self:
        obj = cls.get_namespace().get_ctx()
        if obj is None:
            raise ValueError(f"{cls.__name__} not found in context")
        return obj
    
    @classmethod
    def current_or_none(cls) -> Self | None:
        return cls.get_namespace().get_ctx()

    @classmethod
    async def get(cls: Type[Self], id: Any) -> Self:
        data = await cls.get_namespace().get(id)
        if not data:
            raise ValueError(f"{cls.__name__} with ID '{id}' not found")
        return cls(**data)
    
    
    @classmethod
    async def get_or_none(cls: Type[Self], id: Any) -> Self | None:
        data = await cls.get_namespace().get(id)
        if not data:
            return None
        return cls(**data)


    async def save(self, *args, **kwargs) -> Self:
        
        ns = self.get_namespace()
        
        
        pk_value = getattr(self, ns.primary_key, None)
        
        for field in ns.iter_fields():
            if field.is_foreign_key and getattr(self, field.name) is None:
                fk_cls = field.foreign_cls
                if fk_cls:
                    ctx_instance = fk_cls.get_namespace().get_ctx()
                    if ctx_instance:
                        setattr(self, field.name, ctx_instance.primary_id)

        dump = self.model_dump()

        if pk_value is None:
            # Insert new record
            result = await ns.insert(dump)
        else:
            # Update existing record
            result = await ns.update(pk_value, dump)

        for key, value in result.items():
            setattr(self, key, value)
        return self
    
    async def add(self, model: MODEL | Modelable[MODEL], **kwargs) -> MODEL:
        """Add a model instance to the database"""
        ns = self.get_namespace()
        if isinstance(model, Modelable):
            model = model.to_model()
        relation = ns.get_relation_by_type(model.__class__)
        if not relation:
            raise ValueError(f"Relation model not found for type: {model.__class__.__name__}")
        if relation.is_many_to_many:
            result = await model.save()
            junction = relation.create_junction(
                primary_key=self.primary_id, 
                foreign_key=result.primary_id, 
                **kwargs
            )
            junction = await junction.save()
        else:
            key = getattr(self, relation.primary_key)
            setattr(model, relation.foreign_key, key)
            result = await model.save()
        field = getattr(self, relation.name)
        if field is not None:
            field.append(result)
        return result


    async def delete(self):
        return await self.get_namespace().delete(self.primary_id)
    
    @classmethod
    def _get_context_fields(cls):
        ns = cls.get_namespace()
        where_keys = {}
        for field in ns.iter_fields():
            if field.is_foreign_key:
                if curr:= field.foreign_cls.current_or_none():
                    where_keys[field.name] = curr.primary_id
        return where_keys

    @property
    def primary_id(self):
        ns = self.get_namespace()
        return getattr(self, ns.primary_key)

    @classmethod
    def query(
        cls: Type[Self], 
        fields: list[str] | None = None, 
        alias: str | None = None, 
        use_ctx: bool = True,
        **kwargs
    ) -> "PgSelectQuerySet[Self]":
        from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
        query = PgSelectQuerySet(cls, alias=alias).select(*fields if fields else "*")
        if use_ctx:
            where_keys = cls._get_context_fields()
            if where_keys:
                query.where(**where_keys)
        return query
        # if not fields:
        #     return PgSelectQuerySet(cls, alias=alias).select("*")
        # return PgSelectQuerySet(cls, alias=alias).select(*fields)







