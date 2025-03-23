from enum import Enum
import inspect
import json
from typing import TYPE_CHECKING, Any, Dict, Literal, Type, Optional, List, get_args, get_origin
from typing_extensions import TypeVar
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from promptview.model2.postgres.builder import SQLBuilder
from promptview.model2.postgres.operations import JoinType, PostgresOperations, SelectType
from promptview.model2.versioning import Branch, Turn
from promptview.utils.model_utils import get_list_type, is_list_type
from promptview.model2.base_namespace import DatabaseType, NSManyToManyRelationInfo, NSRelationInfo, Namespace, NSFieldInfo, QuerySet, QuerySetSingleAdapter, SelectFields
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt
if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager
    from promptview.model2.model import Model
    
    
PgIndexType = Literal["btree", "hash", "gin", "gist", "spgist", "brin"]


class PgFieldInfo(NSFieldInfo):
    """PostgreSQL field information"""
    index: PgIndexType | None = None
    sql_type: str
    
    SERIAL_TYPE = "SERIAL"
    
    def __init__(
        self,
        name: str,
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        super().__init__(name, field_type, extra)
        is_primary_key = extra and extra.get("primary_key", False)
        if is_primary_key and name == "id" and field_type is int:
            self.sql_type = PgFieldInfo.SERIAL_TYPE  # Use the constant from SQLBuilder
        else:
            # self.sql_type = PgFieldInfo.to_sql_type(self.data_type, self.is_list)
            self.sql_type = self.build_sql_type()
        if extra and "index" in extra:
            self.index = extra["index"]
            
    def serialize(self, value: Any) -> Any:
        """Serialize the value for the database"""
        if self.sql_type == "JSONB":
            if self.is_list:
                value = json.dumps(value)
            elif self.field_type is BaseModel:
                value = value.model_dump()
        return value
    
    def get_placeholder(self, index: int) -> str:
        """Get the placeholder for the value"""
        if self.sql_type == "JSONB":
            if self.is_list:
                return f'${index}::JSONB'
            else:
                return f'${index}::JSONB'
        elif self.is_temporal:
            return f'${index}::TIMESTAMP'
        else:
            return f'${index}'
    
    def deserialize(self, value: Any) -> Any:
        """Deserialize the value from the database"""
        if self.is_list and type(value) is str:
            return json.loads(value)
        return value
            
    
    def build_sql_type(self) -> str:
        sql_type = None
        
        # if inspect.isclass(self.data_type):
        #     if issubclass(self.data_type, BaseModel):
        #         sql_type = "JSONB"
        #     elif issubclass(self.data_type, Enum):
        #         sql_type = "TEXT"        
        if self.is_temporal:
            sql_type = "TIMESTAMP"
        elif self.is_enum:
            sql_type = self.enum_name
        elif self.is_enum:
            sql_type = "TEXT"
        elif self.data_type is int:
            sql_type = "INTEGER[]" if self.is_list else "INTEGER"
        elif self.data_type is float:
            sql_type = "FLOAT[]" if self.is_list else "FLOAT"
        elif self.data_type is str:
            sql_type = "TEXT[]" if self.is_list else "TEXT"
        elif self.data_type is bool:
            sql_type = "BOOLEAN[]" if self.is_list else "BOOLEAN"
        elif self.data_type is dict:
            sql_type = "JSONB"
        elif issubclass(self.data_type, BaseModel):
            sql_type = "JSONB"
        elif issubclass(self.data_type, Enum):
            sql_type = "TEXT"        
                
        
        if sql_type is None:
            raise ValueError(f"Unsupported field type: {self.data_type}")
        return sql_type
    
    
    @classmethod
    def to_sql_type(cls, field_type: type[Any], extra: dict[str, Any] | None = None) -> str:
        """Map a Python type to a SQL type"""
        db_field_type = None
        if is_list_type(field_type):
            list_type = get_list_type(field_type)
            if list_type is int:
                db_field_type = "INTEGER[]"
            elif list_type is float:
                db_field_type = "FLOAT[]"
            elif list_type is str:
                db_field_type = "TEXT[]"
            elif inspect.isclass(list_type):
                if issubclass(list_type, BaseModel):
                    db_field_type = "JSONB"                        
        else:
            if extra and extra.get("db_type"):
                custom_type = extra.get("db_type")
                if type(custom_type) != str:
                    raise ValueError(f"Custom type is not a string: {custom_type}")
                db_field_type = custom_type
            elif field_type == bool:
                db_field_type = "BOOLEAN"
            elif field_type == int:
                db_field_type = "INTEGER"
            elif field_type == float:
                db_field_type = "FLOAT"
            elif field_type == str:
                db_field_type = "TEXT"
            elif field_type == dt.datetime:
                # TODO: sql_type = "TIMESTAMP WITH TIME ZONE"
                db_field_type = "TIMESTAMP"
            elif isinstance(field_type, dict):
                db_field_type = "JSONB"
            elif isinstance(field_type, type):
                if issubclass(field_type, BaseModel):
                    db_field_type = "JSONB"
                if issubclass(field_type, Enum):
                    db_field_type = "TEXT"                                        
        if db_field_type is None:
            raise ValueError(f"Unsupported field type: {field_type}")
        return db_field_type


MODEL = TypeVar("MODEL", bound="Model")
FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")

class PostgresQuerySet(QuerySet[MODEL]):
    """PostgreSQL implementation of QuerySet"""
    
    def __init__(
        self, 
        model_class: Type[MODEL], 
        namespace: "PostgresNamespace", 
        partition_id: int | None = None, 
        branch_id: int | None = None, 
        joins: list[JoinType] | None = None,
        filters: dict[str, Any] | None = None,
        select: list[list[SelectFields]] | None = None
    ):
        super().__init__(model_class=model_class)
        self.namespace = namespace
        self.partition_id = partition_id
        self.branch_id = branch_id
        self.filters = filters or {}
        self.limit_value = None
        self.offset_value = None
        self.order_by_value = None
        self.include_fields = None
        self.joins = joins or []
        self.select = select or []
    
    def filter(self, **kwargs) -> "PostgresQuerySet[MODEL]":
        """Filter the query"""
        self.filters.update(kwargs)
        return self
    
    def limit(self, limit: int) -> "PostgresQuerySet[MODEL]":
        """Limit the query results"""
        self.limit_value = limit
        return self
    
    def order_by(self, field: str, direction: Literal["asc", "desc"] = "asc") -> "PostgresQuerySet[MODEL]":
        """Order the query results"""
        self.order_by_value = f"{field} {direction}"
        return self
    
    def offset(self, offset: int) -> "PostgresQuerySet[MODEL]":
        """Offset the query results"""
        self.offset_value = offset
        return self
    
    def last(self) -> "QuerySetSingleAdapter[MODEL]":
        """Get the last result"""
        self.limit_value = 1
        self.order_by_value = "created_at desc"
        return QuerySetSingleAdapter(self)
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        """Get the first result"""
        self.limit_value = 1
        self.order_by_value = "created_at asc"
        return QuerySetSingleAdapter(self)
    
    def include(self, fields: list[str]) -> "PostgresQuerySet[MODEL]":
        """Include a relation field in the query results."""
        self.include_fields = fields
        return self
    
    
    async def execute(self) -> List[MODEL]:
        """Execute the query"""
        # Use PostgresOperations to execute the query with versioning support
        if self.select:
            select_types = [SelectType(namespace=sf["namespace"].name, fields=[f.name for f in sf["fields"]]) for sf in self.select]
        else:
            select_types = None
        results = await PostgresOperations.query(
            self.namespace,
            partition_id=self.partition_id,
            branch_id=self.branch_id,
            filters=self.filters,
            limit=self.limit_value,
            order_by=self.order_by_value,
            offset=self.offset_value,
            select=select_types,
            joins=self.joins
        )
        
        # Convert results to model instances if model_class is provided
        if self.model_class:
            instances = [self.model_class(**self.pack_record(data)) for data in results]
            for instance in instances:
                instance._update_relation_instance()
            return instances
        else:
            return results
    
    def pack_record(self, data: Any) -> Any:
        """Pack the record for the model"""
        return self.namespace.pack_record(data)
    



class PostgresNamespace(Namespace[MODEL, PgFieldInfo]):
    """PostgreSQL implementation of Namespace"""
    
    def __init__(
        self, 
        name: str, 
        is_versioned: bool = True, 
        is_repo: bool = False, 
        is_context: bool = False,
        repo_namespace: Optional[str] = None, 
        namespace_manager: Optional["NamespaceManager"] = None
    ):
        super().__init__(name, "postgres", is_versioned, is_repo, is_context, repo_namespace, namespace_manager)
        
    @property
    def table_name(self) -> str:
        return self.name
    
    # def get_field(self, name: str) -> PgFieldInfo:
    #     return super().get_field(name)
        
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
        pg_field = PgFieldInfo(
            name=name,
            field_type=field_type,
            extra=extra,
        )
        if pg_field.is_primary_key:
            if curr_key:= self.find_primary_key() is not None:
                raise ValueError(f"Primary key field {name} already exists. {curr_key} is already the primary key field.")
        self._fields[name] = pg_field
        return pg_field    
    
        # Check if this is a primary key field
        # is_primary_key = extra and extra.get("primary_key", False)
        # is_optional = False
        # if type(None) in get_args(field_type):
        #     nn_types = [t for t in get_args(field_type) if t is not type(None)]
        #     if len(nn_types) != 1:
        #         raise ValueError(f"Field {name} has multiple non-None types: {nn_types}")
        #     field_type = nn_types[0]
        #     is_optional = True
        
        # For auto-incrementing integer primary keys, use SERIAL instead of INTEGER
        # if is_primary_key and name == "id" and field_type is int:
        #     db_field_type = SQLBuilder.SERIAL_TYPE  # Use the constant from SQLBuilder
        # else:
        #     db_field_type = SQLBuilder.map_field_to_sql_type(field_type, extra)
        
        # Get index from extra if available
        # index = None
        # if extra and "index" in extra:
        #     index = extra["index"]
        # print(name)
        # self._fields[name] = PgFieldInfo(
        #     name=name,
        #     field_type=field_type,
        #     db_field_type=db_field_type,
        #     index=index,
        #     # extra=extra or {},
        #     # is_optional=is_optional
        # )
        
    def add_relation(
        self,
        name: str,
        primary_key: str,
        foreign_key: str,
        foreign_cls: "Type[Model]",
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ) -> NSRelationInfo:
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
        # Store the relation information
        
        relation_info = NSRelationInfo(
            namespace=self,
            name=name,
            primary_key=primary_key,
            foreign_key=foreign_key,
            foreign_cls=foreign_cls,
            on_delete=on_delete,
            on_update=on_update,
        )
        self._relations[name] = relation_info
        return relation_info
    
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
    ) -> NSManyToManyRelationInfo:
        """
        Add a many-to-many relation to the namespace.
        
        Args:
            name: The name of the relation
            primary_key: The name of the primary key in the target model
            foreign_key: The name of the foreign key in the target model
            foreign_cls: The class of the target model
            junction_cls: The class of the junction model
            junction_keys: The keys of the junction model
        """
        relation_info = NSManyToManyRelationInfo(
            namespace=self,
            name=name,
            primary_key=primary_key,
            foreign_key=foreign_key,
            foreign_cls=foreign_cls,
            junction_cls=junction_cls,
            junction_keys=junction_keys,
            on_delete=on_delete,
            on_update=on_update,
        )
        self._relations[name] = relation_info
        return relation_info

    
    async def create_namespace(self):
        """
        Create the namespace in the database.
        
        Returns:
            The result of the create operation
        """
        # Create the table
        res = await SQLBuilder.create_table(self)
        
        # Create foreign key constraints for relations
        if self._relations:
            for relation_name, relation_info in self._relations.items():
                await SQLBuilder.create_foreign_key(
                    table_name=self.table_name,
                    column_name=relation_info.primary_key,
                    referenced_table=relation_info.primary_table,
                    referenced_column=relation_info.primary_key,
                    on_delete=relation_info.on_delete,
                    on_update=relation_info.on_update,
                )
        
        return res
    
    
    def pack_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Pack the record for the database"""
        rec = {}
        for key, value in record.items():
            if key in ("id", "branch_id", "turn_id"):
                rec[key] = value
            else:
                field_info = self.get_field(key)
                rec[key] = field_info.deserialize(value)
        return rec
    

    async def drop_namespace(self):
        """
        Drop the namespace from the database.
        
        Returns:
            The result of the drop operation
        """
        res = await SQLBuilder.drop_table(self)
        return res
    
    async def save(self, data: Dict[str, Any], id: Any | None = None, turn: int | Turn | None = None, branch: int | Branch | None = None ) -> Dict[str, Any]:
        """
        Save data to the namespace.
        
        Args:
            data: The data to save
            id: Optional ID to save to
            turn: Optional turn to save to
            branch: Optional branch to save to
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
        
        turn_id, branch_id = self.get_current_ctx_head(turn, branch) if self.is_versioned else (None, None)
        if id is None:
            return await PostgresOperations.insert(self, data, turn_id, branch_id )
        else:
            return await PostgresOperations.update(self, id, data, turn_id, branch_id )
    
    
    async def get(self, id: Any) -> Optional[Dict[str, Any]]:
        """
        Get data from the namespace by ID.
        
        Args:
            id: The ID of the data to get
            
        Returns:
            The data if found, None otherwise
        """
        return await PostgresOperations.get(self, id)
    
    def query(
        self, 
        partition_id: Optional[int] = None, 
        branch: int | Branch | None = None, 
        filters: dict[str, Any] | None = None, 
        joins: list[NSRelationInfo] | None = None,
        select: SelectFields | None = None
    ) -> QuerySet:
        """
        Create a query for this namespace.
        
        Args:
            branch: Optional branch or branch ID to query from            
            
        Returns:
            A query set for this namespace
        """
        branch = self.get_current_ctx_branch(branch) if self.is_versioned else None
        
        return PostgresQuerySet(self.model_class, self, partition_id, branch, select=select, joins=joins, filters=filters, )
        # if self.is_context:            
        #     return PostgresQuerySet(self.model_class, self, partition_id, branch, joins=joins)
        # else:
            
        
        
        
    def partition_query(self, partition_id: int | None = None, branch: int | Branch | None = None, joins: list[NSRelationInfo] | None = None) -> QuerySet:
        """
        Create a query for this namespace.
        """
        return PostgresQuerySet(self.model_class, self, partition_id, branch, joins=joins)