from typing import Any, Dict, Generic, Iterator, Literal, Type, TypeVar, TypedDict, Optional
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


class QuerySet:
    """Base query set interface"""
    
    def filter(self, **kwargs):
        """Filter the query"""
        raise NotImplementedError("Not implemented")
    
    def limit(self, limit: int):
        """Limit the query results"""
        raise NotImplementedError("Not implemented")
    
    async def execute(self):
        """Execute the query"""
        raise NotImplementedError("Not implemented")


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
        """Add a field to the namespace"""
        raise NotImplementedError("Not implemented")
    
    def add_relation(
        self,
        name: str,
        field_info: FieldInfo,
    ):
        """Add a relation to the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def create_namespace(self):
        """Create the namespace in the database"""
        raise NotImplementedError("Not implemented")
    
    async def drop_namespace(self):
        """Drop the namespace from the database"""
        raise NotImplementedError("Not implemented")
    
    async def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save data to the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def get(self, id: Any) -> Optional[Dict[str, Any]]:
        """Get data from the namespace by ID"""
        raise NotImplementedError("Not implemented")
    
    def query(self) -> QuerySet:
        """Create a query for this namespace"""
        raise NotImplementedError("Not implemented")
    
