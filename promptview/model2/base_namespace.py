

from typing import Any, Generic, Iterator, Literal, Type, TypeVar, TypedDict
from pydantic import BaseModel
from pydantic.fields import FieldInfo

DatabaseType = Literal["qdrant", "postgres"]



INDEX_TYPES = TypeVar("INDEX_TYPES", bound=str)


class NSFieldInfo(BaseModel, Generic[INDEX_TYPES]):
    name: str
    field_type: type[Any]
    db_field_type: str
    index: INDEX_TYPES | None = None
    extra: dict[str, Any] | None = None



class Namespace:
    _name: str    
    _fields: dict[str, NSFieldInfo]
    
    def __init__(self, name: str):
        self._name = name
        self._fields = {}
        
    @property
    def name(self) -> str:
        return self._name
    
    def iter_fields(self) -> Iterator[NSFieldInfo]:
        for field in self._fields.values():
            yield field
    
    def add_field(
        self, 
        name: str, 
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        raise NotImplementedError("Not implemented")
    
    def add_relation(
        self, 
        name: str, 
        field_info: FieldInfo,
    ):
        raise NotImplementedError("Not implemented")
    
        
    async def create_namespace(self):
        raise NotImplementedError("Not implemented")
    
    
    async def drop_namespace(self):
        raise NotImplementedError("Not implemented")
    
    
    
    
    
    
    
    
    
    
