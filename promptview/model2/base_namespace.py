from abc import abstractmethod
from enum import Enum
import inspect
from typing import TYPE_CHECKING, Any, Dict, Generic, Iterator, List, Literal, Type, TypeVar, TypedDict, Optional, get_args, get_origin
from pydantic import BaseModel
from pydantic.fields import FieldInfo
import datetime as dt
from promptview.utils.model_utils import is_list_type, unpack_list_model
from promptview.utils.string_utils import camel_to_snake

DatabaseType = Literal["qdrant", "postgres"]

if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager

INDEX_TYPES = TypeVar("INDEX_TYPES", bound=str)


class NSFieldInfo:
    name: str
    field_type: Type[Any]
    origin_type: Type[Any]
    extra: dict[str, Any] | None = None
    is_optional: bool = False
    is_list: bool = False    
    list_origin_type: Type[Any] | None = None
    is_temporal: bool = False
    is_enum: bool = False
    is_literal: bool = False
    enum_values: List[Any] | None = None
    enum_name: str | None = None
    
    def __init__(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        self.name = name        
        self.extra = extra
        self.field_type = field_type
        self.origin_type, self.is_optional = NSFieldInfo.parse_optional(field_type)
        self.list_origin_type, self.is_list = NSFieldInfo.parse_list(self.origin_type)
        if self.is_list and self.list_origin_type is not None:
            self.is_enum, self.enum_values, self.is_literal = NSFieldInfo.parse_enum(self.list_origin_type)
        else:
            self.is_enum, self.enum_values, self.is_literal = NSFieldInfo.parse_enum(self.origin_type)            
        
        if self.is_enum:
            if self.is_literal:
                self.enum_name = camel_to_snake(name) + "_literal"
            else:
                self.enum_name = camel_to_snake(self.data_type.__name__) + "_enum"
            
        if field_type is dt.datetime:
            self.is_temporal = True
        else:
            self.is_temporal = False
            
    @property
    def data_type(self) -> Type[Any]:
        if self.is_list:
            if self.list_origin_type is None:
                raise ValueError("List origin type is not set")
            return self.list_origin_type
        field_type = self.field_type
        if self.is_optional:
            field_type = self.origin_type
        if origin_type := get_origin(field_type):
            return origin_type
        return field_type
    
    def get_enum_values_safe(self) -> List[str]:
        if self.is_enum and self.enum_values is not None:
            return self.enum_values
        else:
            raise ValueError("Field is not an enum")
    
    @classmethod
    def parse_enum(cls, field_type: type[Any]) -> tuple[bool, List[Any] | None, bool]:
        if get_origin(field_type) is Literal:            
            return True, list(get_args(field_type)), True
        if inspect.isclass(field_type) and issubclass(field_type, Enum):
            return True, [e.value for e in field_type], False
        return False, None, False
    
    
    
    @classmethod
    def parse_optional(cls, field_type: type[Any]) -> tuple[type[Any], bool]:
        is_optional = False
        inner_type = field_type
        if type(None) in get_args(field_type):
            nn_types = [t for t in get_args(field_type) if t is not type(None)]
            if len(nn_types) != 1:
                raise ValueError(f"Field has multiple non-None types: {nn_types}")
            inner_type = nn_types[0]
            is_optional = True
        return inner_type, is_optional
    
    
    @classmethod
    def parse_list(cls, field_type: type[Any]) -> tuple[type[Any] | None, bool]:
        if is_list_type(field_type):
            inner_type = unpack_list_model(field_type)
            return inner_type, True
        else:
            return None, False
        
    
    
    def validate_value(self, value: Any) -> bool:
        """Validate the value"""
        if value is None:
            if not self.is_optional:
                return False
            return True
        return True
    
    @abstractmethod
    def serialize(self, value: Any) -> Any:
        """Serialize the value for the database"""
        raise NotImplementedError("Not implemented")
    
    @abstractmethod
    def deserialize(self, value: Any) -> Any:
        """Deserialize the value from the database"""
        raise NotImplementedError("Not implemented")
    
    
class QuerySet:
    """Base query set interface"""
    
    def __init__(self, model_class=None):
        """
        Initialize the query set
        
        Args:
            model_class: Optional model class to use for instantiating results
        """
        self.model_class = model_class
    
    def filter(self, **kwargs):
        """Filter the query"""
        raise NotImplementedError("Not implemented")
    
    def limit(self, limit: int):
        """Limit the query results"""
        raise NotImplementedError("Not implemented")
    
    def order_by(self, field: str, direction: Literal["asc", "desc"] = "asc"):
        """Order the query results"""
        raise NotImplementedError("Not implemented")
    
    def offset(self, offset: int):
        """Offset the query results"""
        raise NotImplementedError("Not implemented")
    
    def last(self):
        """Get the last result"""
        raise NotImplementedError("Not implemented")
    
    def first(self):
        """Get the first result"""
        raise NotImplementedError("Not implemented")
    
    
    async def execute(self):
        """Execute the query"""
        raise NotImplementedError("Not implemented")



FIELD_INFO = TypeVar("FIELD_INFO", bound=NSFieldInfo)

class Namespace(Generic[FIELD_INFO]):
    _name: str
    _fields: dict[str, FIELD_INFO]
    is_versioned: bool
    db_type: DatabaseType
    
    def __init__(
        self, 
        name: str, 
        db_type: DatabaseType,
        is_versioned: bool = False, 
        is_repo: bool = False, 
        repo_namespace: Optional[str] = None,         
        namespace_manager: Optional["NamespaceManager"] = None
    ):
        self._name = name
        self._fields = {}
        self.is_versioned = is_versioned
        self.is_repo = is_repo
        self.repo_namespace = repo_namespace
        self.namespace_manager = namespace_manager
        self.db_type = db_type
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def table_name(self) -> str:
        """Get the table name for this namespace."""
        return self._name
    
    
    def get_field(self, name: str) -> FIELD_INFO:
        return self._fields[name]
    
    def get_repo_namespace(self) -> Optional["Namespace"]:
        if not self.namespace_manager:
            raise ValueError("Namespace manager not set")
        if self.repo_namespace:
            return self.namespace_manager.get_namespace(self.repo_namespace)
        return None
    
    def iter_fields(self) -> Iterator[FIELD_INFO]:
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
        target_namespace: str,
        key: str,
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ):
        """
        Add a relation to the namespace.
        
        Args:
            name: The name of the relation
            target_namespace: The namespace of the target model
            key: The name of the foreign key in the target model
            on_delete: The action to take when the referenced row is deleted
            on_update: The action to take when the referenced row is updated
        """
        raise NotImplementedError("Not implemented")
    
    async def create_namespace(self):
        """Create the namespace in the database"""
        raise NotImplementedError("Not implemented")
    
    async def drop_namespace(self):
        """Drop the namespace from the database"""
        raise NotImplementedError("Not implemented")
    
    async def save(self, data: Dict[str, Any], turn_id: Optional[int] = None, branch_id: Optional[int] = None) -> Dict[str, Any]:
        """Save data to the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def get(self, id: Any) -> Optional[Dict[str, Any]]:
        """Get data from the namespace by ID"""
        raise NotImplementedError("Not implemented")
    
    def query(self, partition_id: Optional[int] = None, branch: Optional[int] = None, model_class=None) -> QuerySet:
        """
        Create a query for this namespace
        
        Args:
            branch: Optional branch ID to query from
            model_class: Optional model class to use for instantiating results
        """
        raise NotImplementedError("Not implemented")
    
