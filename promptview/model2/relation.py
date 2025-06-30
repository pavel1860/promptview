


from typing import TYPE_CHECKING, Generic, Type, TypeVar, Any
from pydantic_core import core_schema
from pydantic import GetCoreSchemaHandler





if TYPE_CHECKING:
    from promptview.model2.base_namespace import NSRelationInfo, Namespace
    from promptview.model2.model import Model
    from promptview.model2.postgres.query_set3 import SelectQuerySet


FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")

class Relation(Generic[FOREIGN_MODEL], list):
    
    
    def __init__(self, *args, relation: "NSRelationInfo | None" = None, **kwargs):        
        items = []
        self._is_initialized = False 
        self._primary_instance = None
        self._relation = relation
        if len(args) == 1 and isinstance(args[0], list):
            self._is_initialized = True
            items = [self.pack_cls(item) for item in args[0]]
        
        super().__init__(items)
        
        
    # def __repr__(self) -> str:
    #     if not self._is_initialized:
    #         return f"Relation({self._relation.primary_cls.__name__} -> {self._relation.foreign_cls.__name__})"
    #     return "Relation[\n" + ",\n".join("  " +repr(item) for item in self) + "\n]"
    
    @property
    def primary_id(self) -> Any:
        if self._primary_instance is None:
            raise ValueError("Primary instance is not set")
        return self._primary_instance.id
    
    def set_primary_instance(self, primary_instance: "Model"):
        self._primary_instance = primary_instance
    
    def pack_cls(self, item: Any) -> Any:  
        if self._relation is None:
            raise ValueError("Relation is not set")
        item = self._relation.foreign_namespace.pack_record(item)
        return self._relation.inst_foreign_model(item)


    def query(self) -> "SelectQuerySet[FOREIGN_MODEL]":
        if self._relation is None:
            raise ValueError("Relation is not set")
        where_dict = {self._relation.foreign_key: self.primary_id}
        return self._relation.foreign_cls.query().where(**where_dict).order_by("created_at")
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize
            )
        )
    
    @staticmethod
    def _validate(value: Any) -> "Relation":
        if isinstance(value, Relation):
            return value
        if isinstance(value, list):
            return Relation[Relation](value)
        raise ValueError(f"Invalid value: {value}")
    
    @staticmethod
    def _serialize(instance: "Relation | None") -> list | None:
        if instance is None:
            return None
        return instance
    
    