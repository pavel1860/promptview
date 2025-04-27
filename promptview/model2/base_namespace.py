from abc import abstractmethod
from enum import Enum
import inspect
import json
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Generic, Iterator, List, Literal, Type, TypeVar, TypedDict, Optional, get_args, get_origin
import uuid
from pydantic import BaseModel
from pydantic.fields import FieldInfo
import datetime as dt

from promptview.utils.model_utils import is_list_type, unpack_list_model
from promptview.utils.string_utils import camel_to_snake

DatabaseType = Literal["qdrant", "postgres"]

if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager
    from promptview.model2.model import Model
    from promptview.model2.versioning import Branch, Turn, Partition
INDEX_TYPES = TypeVar("INDEX_TYPES", bound=str)



class SelectFields(TypedDict):
    namespace: "Namespace"
    fields: "list[NSFieldInfo]"

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
    is_foreign_key: bool = False
    is_literal: bool = False
    enum_values: List[Any] | None = None
    enum_name: str | None = None
    is_key: bool = False
    is_primary_key: bool = False
    db_type: str | None = None
    
    def __init__(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        self.name = name        
        self.extra = extra
        self.is_foreign_key = extra and extra.get("foreign_key", False)
        self.field_type = field_type
        self.db_type = extra and extra.get("db_type", None)
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

        if self.origin_type is dt.datetime:
            self.is_temporal = True
        else:
            self.is_temporal = False
        
        if extra:
            if not extra.get("is_relation", False):
                self.is_primary_key = extra.get("primary_key", False)
                    
        self.is_key = extra and extra.get("is_key", False)
        if self.is_key:
            self.key_type = extra and extra.get("type", None)
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
            if not self.is_optional and not self.is_foreign_key and not self.is_key:
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


MODEL = TypeVar("MODEL", bound="Model")
FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")
class NSRelationInfo(Generic[MODEL, FOREIGN_MODEL]):
    name: str
    foreign_cls: Type[FOREIGN_MODEL]
    primary_key: str
    foreign_key: str
    on_delete: str
    on_update: str
    namespace: "Namespace"
    _primary_cls: Type[MODEL] | None = None
    
    def __init__(
        self, 
        namespace: "Namespace",
        name: str,         
        primary_key: str,
        foreign_key: str,
        foreign_cls: Type[FOREIGN_MODEL],
        on_delete: str = "CASCADE", 
        on_update: str = "CASCADE",        
    ):
        self.name = name
        self.primary_key = primary_key
        self.foreign_key = foreign_key
        self.foreign_cls = foreign_cls
        self.on_delete = on_delete
        self.on_update = on_update
        self.namespace = namespace
    @property
    def primary_cls(self) -> Type[MODEL]:
        if self._primary_cls is None:
            raise ValueError("Primary class not set")
        return self._primary_cls
    
    def set_primary_cls(self, primary_cls: Type[MODEL]):
        self._primary_cls = primary_cls
        
    @property
    def foreign_table(self) -> str:
        return self.foreign_cls.get_namespace_name()
    
    @property
    def primary_table(self) -> str:
        return self.primary_cls.get_namespace_name()
    
    @property
    def primary_namespace(self) -> "Namespace":
        return self.primary_cls.get_namespace()
    
    @property
    def foreign_namespace(self) -> "Namespace":
        return self.foreign_cls.get_namespace()
    
    
    def deserialize(self, value: Any) -> Any:
        json_value = json.loads(value)
        return json_value
     
    
JUNCTION_MODEL = TypeVar("JUNCTION_MODEL", bound="Model")

class NSManyToManyRelationInfo(Generic[MODEL, FOREIGN_MODEL, JUNCTION_MODEL], NSRelationInfo[MODEL, FOREIGN_MODEL]):
    """Many to many relation"""
    junction_cls: Type[JUNCTION_MODEL]
    junction_keys: list[str]

    def __init__(
        self,
        namespace: "Namespace",
        name: str,
        primary_key: str,
        foreign_key: str,
        foreign_cls: Type[FOREIGN_MODEL],
        junction_cls: Type[JUNCTION_MODEL],
        junction_keys: list[str],
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE"
    ):
        super().__init__(namespace, name, primary_key, foreign_key, foreign_cls, on_delete, on_update)
        self.junction_cls = junction_cls
        self.junction_keys = junction_keys

    
    @property
    def junction_table(self) -> str:
        return self.junction_cls.get_namespace_name()

    @property  
    def junction_namespace(self) -> "Namespace":
        return self.junction_cls.get_namespace()

    @property
    def junction_primary_key(self) -> str:
        return self.junction_keys[0]
    
    @property
    def junction_foreign_key(self) -> str:
        return self.junction_keys[1]
    
T_co = TypeVar("T_co", covariant=True)

class QuerySetSingleAdapter(Generic[T_co]):
    def __init__(self, queryset: "QuerySet[T_co]"):
        self.queryset = queryset

    def __await__(self) -> Generator[Any, None, T_co]:
        async def await_query():
            results = await self.queryset.execute()
            if results:
                return results[0]
            return None
            # raise ValueError("No results found")
            # return None
            # raise DoesNotExist(self.queryset.model)
        return await_query().__await__()  


# MODEL = TypeVar("MODEL", bound="Model")
    
class QuerySet(Generic[MODEL]):
    """Base query set interface"""
    model_class: Type[MODEL]
    
    def __init__(self, model_class: Type[MODEL]):
        """
        Initialize the query set
        
        Args:
            model_class: Optional model class to use for instantiating results
        """
        self.model_class = model_class
        
    def __await__(self):
        """Make the query awaitable"""
        return self.execute().__await__()
    
    def filter(self, filter_fn: Callable[[MODEL], bool] | None = None, **kwargs) -> "QuerySet[MODEL]":
        """Filter the query"""
        raise NotImplementedError("Not implemented")
    
    def set_filter(self, *args, **kwargs) -> "QuerySet[MODEL]":
        """Set the filters for the query"""
        raise NotImplementedError("Not implemented")
    
    def limit(self, limit: int) -> "QuerySet[MODEL]":
        """Limit the query results"""
        raise NotImplementedError("Not implemented")
    
    def order_by(self, field: str, direction: Literal["asc", "desc"] = "asc") -> "QuerySet[MODEL]":
        """Order the query results"""
        raise NotImplementedError("Not implemented")
    
    def turn_limit(self, limit: int, order_direction: Literal["asc", "desc"] = "desc") -> "QuerySet[MODEL]":
        """Limit the query results to the last N turns"""
        raise NotImplementedError("Not implemented")
    
    def offset(self, offset: int) -> "QuerySet[MODEL]":
        """Offset the query results"""
        raise NotImplementedError("Not implemented")
    
    def last(self)-> "QuerySetSingleAdapter[MODEL]":
        """Get the last result"""
        raise NotImplementedError("Not implemented")
    
    def tail(self, limit: int = 10) -> "QuerySet[MODEL]":
        """Get the last N results"""
        raise NotImplementedError("Not implemented")
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        """Get the first result"""
        raise NotImplementedError("Not implemented")
    
    def head(self, limit: int = 10) -> "QuerySet[MODEL]":
        """Get the first N results"""
        raise NotImplementedError("Not implemented")
    
    async def execute(self) -> List[MODEL]:
        """Execute the query"""
        raise NotImplementedError("Not implemented")

    def join(self, *models: "Type[Model]") -> "QuerySet[MODEL]":
        """Join the query"""
        raise NotImplementedError("Not implemented")
    
    def sub_query(self, query_set: "QuerySet") -> "QuerySet[MODEL]":
        """Create a sub query"""
        raise NotImplementedError("Not implemented")

FIELD_INFO = TypeVar("FIELD_INFO", bound=NSFieldInfo)


class Namespace(Generic[MODEL, FIELD_INFO]):
    _model_cls: Type[MODEL] | None = None
    _name: str
    _fields: dict[str, FIELD_INFO]
    _relations: dict[str, NSRelationInfo]
    is_versioned: bool
    is_artifact: bool
    is_repo: bool
    db_type: DatabaseType
    _primary_key: FIELD_INFO | None = None
    def __init__(
        self, 
        name: str, 
        db_type: DatabaseType,
        is_versioned: bool = False, 
        is_repo: bool = False, 
        is_artifact: bool = False,
        is_context: bool = False,
        repo_namespace: Optional[str] = None,         
        namespace_manager: Optional["NamespaceManager"] = None
    ):
        self._name = name
        self._fields = {}
        self._relations = {}
        self.is_versioned = is_versioned
        self.is_repo = is_repo
        self.is_context = is_context
        self.is_artifact = is_artifact
        self.repo_namespace = repo_namespace
        self.namespace_manager = namespace_manager
        self.db_type = db_type
        self._model_cls = None
        self._primary_key = None

       
        
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def table_name(self) -> str:
        """Get the table name for this namespace."""
        return self._name
    
    @property
    def model_class(self) -> Type[MODEL]:
        if self._model_cls is None:
            raise ValueError("Model class not set")
        return self._model_cls
    
    @property
    def primary_key(self) -> FIELD_INFO:
        if self.is_versioned:
            return self._fields["artifact_id"]
        if self._model_cls is None:
            raise ValueError("Model class not set")
        if self._primary_key is None:
            self._primary_key = self.find_primary_key()
            if self._primary_key is None:
                raise ValueError("Primary key not found")
        return self._primary_key
    
    def find_primary_key(self) -> FIELD_INFO | None:
        for field_name, field_info in self._fields.items():
            if field_info.is_primary_key:
                return field_info
        return None
    
    def set_model_class(self, model_class: Type[MODEL]):
        self._model_cls = model_class
        for relation_info in self._relations.values():
            relation_info.set_primary_cls(model_class)
    
    
    
    def get_field(self, name: str) -> FIELD_INFO | None:
        return self._fields.get(name, None)
    
    def has_field(self, name: str) -> bool:
        return name in self._fields
    
    def has_relation(self, name: str) -> bool:
        return name in self._relations
    
    def get_relation(self, name: str) -> NSRelationInfo | None:
        return self._relations.get(name, None)
    
    
    def get_relation_by_type(self, model: Type[MODEL]) -> NSRelationInfo | None:
        for rel in self._relations.values():
            if rel.foreign_cls == model:
                return rel
        return None
    
    
    def get_repo_namespace(self) -> Optional["Namespace"]:
        if not self.namespace_manager:
            raise ValueError("Namespace manager not set")
        if self.repo_namespace:
            return self.namespace_manager.get_namespace(self.repo_namespace)
        return None
    
    def iter_fields(self) -> Iterator[FIELD_INFO]:
        for field in self._fields.values():
            yield field
            
    def iter_relations(self) -> Iterator[NSRelationInfo]:
        for relation in self._relations.values():
            yield relation
            
    def get_field_names(self) -> list[str]:
        return list(self._fields.keys())
    
    def select_fields(self, fields: list[str] | None = None) -> SelectFields:
        
        if fields is None:
            return SelectFields(
                namespace=self,
                fields=[f for f in self._fields.values()]
            )
        return SelectFields(
            namespace=self,
            fields=[self._fields[field] for field in fields]
        )
    
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
        primary_key: str,
        foreign_key: str,
        foreign_cls: Type["Model"],        
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ):
        """
        Add a relation to the namespace.
        
        Args:
            name: The name of the relation
            primary_key: The name of the primary key in the target model
            foreign_key: The name of the foreign key in the target model
            foreign_cls: The class of the target model
            on_delete: The action to take when the referenced row is deleted
            on_update: The action to take when the referenced row is updated
        """
        raise NotImplementedError("Not implemented")
    
    def add_many_relation(
        self,
        name: str,
        primary_key: str,
        foreign_key: str,
        foreign_cls: Type["Model"],
        junction_cls: Type["Model"],
        junction_keys: list[str],
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ):
        """
        Add a many to many relation to the namespace.
        
        Args:
            name: The name of the relation
            primary_key: The name of the primary key in the target model
            foreign_key: The name of the foreign key in the target model
            foreign_cls: The class of the target model
            junction_cls: The class of the junction model
            junction_keys: The keys of the junction model
            on_delete: The action to take when the referenced row is deleted
            on_update: The action to take when the referenced row is updated
        """
        raise NotImplementedError("Not implemented")
    
    async def get_current_ctx_head(self, turn: "int | Turn | None" = None, branch: "int | Branch | None" = None) -> tuple[int | None, int | None]:
        from promptview.model2.context import Context
        turn_id, branch_id = await Context.get_current_head(turn, branch)
        if self.is_versioned:
            if turn_id is None:
                raise ValueError(f"""Turn is required when saving {self.model_class.__name__} to an artifact""")
            if branch_id is None:
                raise ValueError(f"""Branch is required when saving {self.model_class.__name__} to an artifact""")
        return turn_id, branch_id
    
        
    async def get_current_ctx_branch(self, branch: "int | Branch | None" = None) -> int | None:
        from promptview.model2.context import Context
        return await Context.get_current_branch(branch)
    
    async def get_current_ctx_partition_branch(self, partition: "int| Partition | None", branch: "int | Branch | None" = None):        
        from promptview.model2.context import Context
        partition = await Context.get_current_partition(partition)
        branch = await Context.get_current_branch(branch)        
        return partition, branch
    
    async def create_namespace(self):
        """Create the namespace in the database"""
        raise NotImplementedError("Not implemented")
    
    async def drop_namespace(self):
        """Drop the namespace from the database"""
        raise NotImplementedError("Not implemented")
    
    # async def save(self, data: Dict[str, Any], id: Any | None = None, artifact_id: uuid.UUID | None = None, version: int | None = None, turn: "int | Turn | None" = None, branch: "int | Branch | None" = None) -> Dict[str, Any]:
    #     """Save data to the namespace"""
    #     raise NotImplementedError("Not implemented")
    
    async def save(self, model: MODEL) -> MODEL:
        """Save data to the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def get(self, id: Any) -> MODEL | None:
        """Get data from the namespace by ID"""
        raise NotImplementedError("Not implemented")
    
    async def get_artifact(self, artifact_id: uuid.UUID, version: int | None = None) -> MODEL | None:
        """Get data from the namespace by artifact ID and version"""
        raise NotImplementedError("Not implemented")
    
    async def delete(self, id: Any) -> MODEL | None:
        """Delete data from the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def delete_model(self, model: MODEL) -> MODEL | None:
        """Delete data from the namespace"""
        raise NotImplementedError("Not implemented")

    
    def query(
        self, 
        partition_id: int | None = None, 
        branch: "int | Branch | None" = None, 
        filters: dict[str, Any] | None = None, 
        joins: list[Any] | None = None,
        select: SelectFields | None = None,
        **kwargs
    ) -> QuerySet:
        """
        Create a query for this namespace
        
        Args:
            branch: Optional branch or branch ID to query from            
        """
        raise NotImplementedError("Not implemented")
    
