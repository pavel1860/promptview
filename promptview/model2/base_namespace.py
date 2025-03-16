from typing import TYPE_CHECKING, Any, Dict, Generic, Iterator, Literal, Type, TypeVar, TypedDict, Optional
from pydantic import BaseModel
from pydantic.fields import FieldInfo

DatabaseType = Literal["qdrant", "postgres"]

if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager

INDEX_TYPES = TypeVar("INDEX_TYPES", bound=str)


class NSFieldInfo(BaseModel, Generic[INDEX_TYPES]):
    name: str
    field_type: Any
    db_field_type: str
    index: INDEX_TYPES | None = None
    extra: dict[str, Any] | None = None
    is_optional: bool = False


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
    
    async def execute(self):
        """Execute the query"""
        raise NotImplementedError("Not implemented")


class Namespace:
    _name: str
    _fields: dict[str, NSFieldInfo]
    is_versioned: bool
    
    def __init__(
        self, 
        name: str, 
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
        
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def table_name(self) -> str:
        """Get the table name for this namespace."""
        return self._name
    
    
    def get_repo_namespace(self) -> Optional["Namespace"]:
        if not self.namespace_manager:
            raise ValueError("Namespace manager not set")
        if self.repo_namespace:
            return self.namespace_manager.get_namespace(self.repo_namespace)
        return None
    
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
    
    async def save(self, data: Dict[str, Any], branch_id: Optional[int] = None, turn_id: Optional[int] = None) -> Dict[str, Any]:
        """Save data to the namespace"""
        raise NotImplementedError("Not implemented")
    
    async def get(self, id: Any) -> Optional[Dict[str, Any]]:
        """Get data from the namespace by ID"""
        raise NotImplementedError("Not implemented")
    
    def query(self, branch: Optional[int] = None, model_class=None) -> QuerySet:
        """
        Create a query for this namespace
        
        Args:
            branch: Optional branch ID to query from
            model_class: Optional model class to use for instantiating results
        """
        raise NotImplementedError("Not implemented")
    
