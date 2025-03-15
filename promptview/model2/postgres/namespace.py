from typing import Any, Dict, Literal, Type, Optional, List
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from promptview.model2.postgres.builder import SQLBuilder
from promptview.model2.postgres.operations import PostgresOperations
from promptview.utils.model_utils import get_list_type, is_list_type
from promptview.model2.base_namespace import Namespace, NSFieldInfo, QuerySet
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt

PgIndexType = Literal["btree", "hash", "gin", "gist", "spgist", "brin"]


class PgFieldInfo(NSFieldInfo[PgIndexType]):
    """PostgreSQL field information"""
    pass


class PostgresQuerySet(QuerySet):
    """PostgreSQL implementation of QuerySet"""
    
    def __init__(self, namespace: "PostgresNamespace"):
        self.namespace = namespace
        self.filters = {}
        self.limit_value = None
        self.offset_value = None
        self.order_by_value = None
    
    def filter(self, **kwargs):
        """Filter the query"""
        self.filters.update(kwargs)
        return self
    
    def limit(self, limit: int):
        """Limit the query results"""
        self.limit_value = limit
        return self
    
    async def execute(self) -> List[Dict[str, Any]]:
        """Execute the query"""
        # Implementation would execute the query
        # This would use SQLBuilder to generate and execute SELECT SQL
        # For now, just return dummy data
        return [{"id": 1, "name": "Example", "age": 30}]
    
    def __await__(self):
        """Make the query awaitable"""
        return self.execute().__await__()


class PostgresNamespace(Namespace):
    """PostgreSQL implementation of Namespace"""
    
    def __init__(self, name: str):
        super().__init__(name)
        
    @property
    def table_name(self) -> str:
        return self.name
        
    def add_field(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        """
        Add a field to the namespace.
        
        Args:
            name: The name of the field
            field_type: The type of the field
            extra: Extra metadata for the field
        """
        # Check if this is a primary key field
        is_primary_key = extra and extra.get("primary_key", False)
        
        # For auto-incrementing integer primary keys, use SERIAL instead of INTEGER
        if is_primary_key and name == "id" and field_type == int:
            db_field_type = SQLBuilder.SERIAL_TYPE  # Use the constant from SQLBuilder
        else:
            db_field_type = SQLBuilder.map_field_to_sql_type(field_type, extra)
        
        # Get index from extra if available
        index = None
        if extra and "index" in extra:
            index = extra["index"]

        self._fields[name] = PgFieldInfo(
            name=name,
            field_type=field_type,
            db_field_type=db_field_type,
            index=index,
            extra=extra or {},
        )
        
    def add_relation(
        self,
        name: str,
        field_info: FieldInfo,
    ):
        """
        Add a relation to the namespace.
        
        Args:
            name: The name of the relation
            field_info: The field information for the relation
        """
        # Implementation for relations
        pass

    async def create_namespace(self):
        """
        Create the namespace in the database.
        
        Returns:
            The result of the create operation
        """
        res = await SQLBuilder.create_table(self)
        return res

    async def drop_namespace(self):
        """
        Drop the namespace from the database.
        
        Returns:
            The result of the drop operation
        """
        res = await SQLBuilder.drop_table(self)
        return res
    
    async def save(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save data to the namespace.
        
        Args:
            data: The data to save
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
        return await PostgresOperations.save(self, data)
    
    async def get(self, id: Any) -> Optional[Dict[str, Any]]:
        """
        Get data from the namespace by ID.
        
        Args:
            id: The ID of the data to get
            
        Returns:
            The data if found, None otherwise
        """
        return await PostgresOperations.get(self, id)
    
    def query(self) -> QuerySet:
        """
        Create a query for this namespace.
        
        Returns:
            A query set for this namespace
        """
        return PostgresQuerySet(self)
        