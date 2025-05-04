import textwrap
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Literal, Type, Optional, List, TypeVar, get_args, get_origin
import uuid
from promptview.model2.postgres.builder import SQLBuilder
from promptview.model2.postgres.operations import JoinType, PostgresOperations, SelectType

from promptview.model2.postgres.query_set import PostgresQuerySet
from promptview.model2.postgres.query_set3 import SelectQuerySet
from promptview.model2.versioning import ArtifactLog, Branch, Turn

from promptview.model2.base_namespace import DatabaseType, NSManyToManyRelationInfo, NSRelationInfo, Namespace, NSFieldInfo, QuerySet, QuerySetSingleAdapter, SelectFields
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt
from promptview.model2.postgres.fields_query import PgFieldInfo, QueryField, NamespaceQueryFields
if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager
    from promptview.model2.model import Model
    
    

MODEL = TypeVar("MODEL", bound="Model")
FOREIGN_MODEL = TypeVar("FOREIGN_MODEL", bound="Model")

        

    



class PostgresNamespace(Namespace[MODEL, PgFieldInfo]):
    """PostgreSQL implementation of Namespace"""
    
    def __init__(
        self, 
        name: str, 
        is_versioned: bool = True, 
        is_repo: bool = False, 
        is_context: bool = False,
        is_artifact: bool = False,
        repo_namespace: Optional[str] = None, 
        namespace_manager: Optional["NamespaceManager"] = None
    ):
        super().__init__(
            name=name, 
            db_type="postgres", 
            is_versioned=is_versioned, 
            is_repo=is_repo, 
            is_context=is_context, 
            is_artifact=is_artifact, 
            repo_namespace=repo_namespace, 
            namespace_manager=namespace_manager
        )

        
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
    
    
    # def get_relation(self, relation_name: str) -> NSRelationInfo:
    #     return self._relations[relation_name]
    
    def get_relation_joins(self, relation_name: str, primary_alias: str | None = None, foreign_alias: str | None = None) -> list[JoinType]:
        relation_info = self._relations[relation_name]
        return [{
            "primary_table": primary_alias or relation_info.primary_table,
            "primary_key": relation_info.primary_key,
            "foreign_table": foreign_alias or relation_info.foreign_table,
            "foreign_key": relation_info.foreign_key,
        }]

    
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
                if relation_info.primary_key == "artifact_id":
                    # can't enforce foreign key constraint on artifact_id because it's not a single record
                    continue
                await SQLBuilder.create_foreign_key(
                    table_name=self.table_name,
                    column_name=relation_info.primary_key,
                    column_type=self.get_field(relation_info.primary_key).sql_type,
                    referenced_table=relation_info.primary_table,
                    referenced_column=relation_info.primary_key,
                    on_delete=relation_info.on_delete,
                    on_update=relation_info.on_update,
                )
        
        return res
    
    
    def pack_record(self, record: Dict[str, Any]) -> MODEL:
        """Pack the record for the database"""
        rec = {}
        for key, value in record.items():
            key = key.strip('"').strip("'")
            if key in ("id", "branch_id", "turn_id"):
                rec[key] = value
            else:
                if self.has_field(key):
                    field_info = self.get_field(key)
                    if not field_info:
                        raise ValueError(f"Unknown key: {key}")
                    rec[key] = field_info.deserialize(value)
                elif self.has_relation(key):
                    relation_info = self.get_relation(key)
                    if not relation_info:
                        raise ValueError(f"Unknown key: {key}")
                    rec[key] = relation_info.deserialize(value)
                else:
                    raise ValueError(f"Unknown key: {key}")
        return rec
    

    async def drop_namespace(self):
        """
        Drop the namespace from the database.
        
        Returns:
            The result of the drop operation
        """
        res = await SQLBuilder.drop_table(self)
        return res
    
    
    def get_fields_insert(self, model_dump: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Get the fields to insert into the database"""
        keys = []
        placeholders = []
        values = []
        
        for field in self._fields.values():
            if not field.is_key or field.name == "artifact_id":
                value = model_dump.get(field.name)                
                if field.validate_value(value):
                    placeholder = field.get_placeholder(len(values) + 1)
                    processed_value = field.serialize(value)                    
                    keys.append(f'"{field.name}"')
                    placeholders.append(placeholder)
                    values.append(processed_value)
                else:
                    raise ValueError(f"Field {field.name} is not valid")
        return {k: {"key": k, "placeholder": p, "value": v} for k, p, v in zip(keys, placeholders, values)}
    
    
    def build_insert_query(self, model_dump: dict[str, Any]) -> tuple[str, list[Any]]:
        """Build an insert query for the model"""                
        keys = []
        placeholders = []
        values = []
        
        for field in self._fields.values():
            if not field.is_key or field.name == "artifact_id":
                value = model_dump.get(field.name)                
                if field.validate_value(value):
                    placeholder = field.get_placeholder(len(values) + 1)
                    processed_value = field.serialize(value)                    
                    keys.append(f'"{field.name}"')
                    placeholders.append(placeholder)
                    values.append(processed_value)
                else:
                    raise ValueError(f"Field {field.name} is not valid")
        
        
        sql = (
            f"""INSERT INTO "{self.table_name}" ({", ".join(keys)})\n"""
            f"""VALUES ({", ".join(placeholders)})\n"""
            f"""RETURNING *\n"""
        )
        return sql, values
    
    
    def get_fields_update(self, model_dump: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        """Get the fields to update in the database"""
        keys = []
        placeholders = []
        values = []
        key = None
        key_placeholder = None
        key_value = None
        
        for field in self._fields.values():
            value = model_dump.get(field.name)
            if field.validate_value(value):
                placeholder = field.get_placeholder(len(values) + 1)
                processed_value = field.serialize(value)
                if field.is_key:
                    key=processed_value
                    key_placeholder = placeholder
                    key_value = value
                else:
                    keys.append(f'"{field.name}"')
                    placeholders.append(placeholder)
                    values.append(processed_value)
            else:
                raise ValueError(f"Field {field.name} is not valid")
        if key is None:
            raise ValueError("Primary key is required")
        key_field = {"key": key, "placeholder": key_placeholder, "value": key_value}
        fields = {k: {"key": k, "placeholder": p, "value": v} for k, p, v in zip(keys, placeholders, values)}
        return key_field, fields

    
    def build_update_query(self, model_dump: dict[str, Any]) -> tuple[str, list[Any]]:
        """Build an update query for the model"""
        set_parts = []
        values = []
        key = None
        
        for field in self._fields.values():
            value = model_dump.get(field.name)
            if field.validate_value(value):
                placeholder = field.get_placeholder(len(values) + 1)
                processed_value = field.serialize(value)
                if field.is_key:
                    key=processed_value
                else:           
                    set_parts.append(f'"{field.name}" = {placeholder}')
                    values.append(processed_value)
            else:
                raise ValueError(f"Field {field.name} is not valid")
        if key is None:
            raise ValueError("Primary key is required")
        values.append(key)

        set_clause = ", \n".join(set_parts)
        sql = (
            f"""UPDATE "{self.table_name}"\n"""
            f"""SET \n{textwrap.indent(set_clause, "    ")}\n"""
            f"""WHERE {self.primary_key.name} = ${len(values)}\n"""
            f"""RETURNING *\n"""
        )
        return sql, values
    # async def save(self, data: Dict[str, Any], id: Any | None = None, artifact_id: uuid.UUID | None = None, version: int | None = None, turn: int | Turn | None = None, branch: int | Branch | None = None ) -> Dict[str, Any]:
    #     """
    #     Save data to the namespace.
        
    #     Args:
    #         data: The data to save
    #         id: Optional ID to save to
    #         turn: Optional turn to save to
    #         branch: Optional branch to save to
            
    #     Returns:
    #         The saved data with any additional fields (e.g., ID)
    #     """
        
    #     turn_id, branch_id = await self.get_current_ctx_head(turn, branch) if self.is_versioned else (None, None)
    #     if artifact_id is not None:
    #         if not version:
    #             raise ValueError("Version is required when saving to an artifact")
    #         data["artifact_id"] = artifact_id
    #         data["version"] = version
    #         data["updated_at"] = dt.datetime.now()
    #         record = await PostgresOperations.insert(self, data, turn_id, branch_id )
    #     elif id is None:
    #         record = await PostgresOperations.insert(self, data, turn_id, branch_id )
    #     else:
    #         record = await PostgresOperations.update(self, id, data, turn_id, branch_id )
    #     return self.pack_record(record)
    
    def validate_model_fields(self, model: MODEL) -> MODEL:
        """Validate the model fields"""
        from promptview.model2.namespace_manager import NamespaceManager
        for field in self._fields.values():
            if field.is_foreign_key:
                if getattr(model, field.name) is None:
                    relation = NamespaceManager.get_reversed_relation(self.table_name, field.name)
                    if relation is None:
                        raise ValueError(f"""Field "{field.name}" on model "{self.model_class.__name__}" is a key field but has no reversed relation""")
                    curr_rel_model = relation.primary_cls.current()
                    if curr_rel_model is None:
                        raise ValueError(f"""Field "{field.name}" on model "{self.model_class.__name__}" is a key field but no context was found for class "{relation.primary_cls.__name__}".""")
                    setattr(model, field.name, curr_rel_model.id)
        return model
    
    
    async def save(self, model: MODEL) -> MODEL:
        """
        Save data to the namespace.
        
        Args:
            model: The model to save
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
        model = self.validate_model_fields(model)
        if getattr(model, self.primary_key.name) is None:
            dump = model.model_dump()
            if self.is_artifact:
                dump["artifact_id"] = uuid.uuid4()                            
            sql, values = self.build_insert_query(model.model_dump())
        else:
            dump = model.model_dump()
            if self.is_artifact:
                dump["version"] = model.version + 1
                dump["updated_at"] = dt.datetime.now()
                sql, values = self.build_insert_query(model.model_dump())
            else:
                sql, values = self.build_update_query(dump)
            
        record = await PGConnectionManager.fetch_one(sql, *values)
        if record is None:
            raise ValueError("Failed to save model")
        return self.pack_record(dict(record))
    
    

    
    # async def delete(self, data: Dict[str, Any] | None = None, id: Any | None = None, artifact_id: uuid.UUID | None = None, version: int | None = None, turn: "int | Turn | None" = None, branch: "int | Branch | None" = None) -> Dict[str, Any]:
    #     """Delete data from the namespace"""
    #     turn_id, branch_id = await self.get_current_ctx_head(turn, branch) if self.is_versioned else (None, None)
    #     if artifact_id is not None:
    #         if not version:
    #             raise ValueError("Version is required when saving to an artifact")
    #         if data is None:
    #             raise ValueError("Data is required when deleting an artifact")
    #         data["artifact_id"] = artifact_id
    #         data["version"] = version
    #         # data["updated_at"] = dt.datetime.now()
    #         data["deleted_at"] = dt.datetime.now()
    #         record = await PostgresOperations.update(self, id, data, turn_id, branch_id )
    #     else:
    #         if id is None:
    #             raise ValueError("Either id or artifact_id must be provided")
    #         record = await PostgresOperations.delete(self, id)
    #     return self.pack_record(record)
    
    async def delete(self, id: Any) -> MODEL | None:
        """Delete data from the namespace"""
        sql = f"""
        DELETE FROM "{self.table_name}" WHERE id = $1
        RETURNING *;
        """        
        # Execute query
        result = await PGConnectionManager.fetch_one(sql, id)
        return self.pack_record(dict(result)) if result else None
    
    async def delete_model(self, model: MODEL) -> MODEL | None:
        """Delete data from the namespace"""
        return await self.delete(model.primary_id)
    
    
    async def delete_artifact(self, model: MODEL) -> MODEL | None:
        """Delete data from the namespace by artifact ID and version."""        
        model_dump = model.model_dump()
        model_dump["deleted_at"] = dt.datetime.now()
        model_dump["version"] = model.version + 1
        sql, values = self.build_insert_query(model_dump)
        result = await PGConnectionManager.execute(sql, *values)
        return self.pack_record(dict(result)) if result else None
        
        
        
        
    async def get(self, id: Any) -> MODEL | None:
        """
        Get data from the namespace by ID.
        
        Args:
            id: The ID of the data to get
            
        Returns:
            The data if found, None otherwise
        """
        # res = await PostgresOperations.get(self, id)
        # if res is None:
            # return None
        sql = f'SELECT * FROM "{self.table_name}" WHERE id = $1;'        
        # Execute query
        result = await PGConnectionManager.fetch_one(sql, id)
        return self.pack_record(dict(result)) if result else None
    
    
    async def get_artifact(self, artifact_id: uuid.UUID, version: int | None = None) -> MODEL | None:
        """
        Get data from the namespace by artifact ID and version.
        """
        if version is not None:
            sql = f'SELECT * FROM "{self.table_name}" WHERE artifact_id = $1 AND version = $2;'
            values = [artifact_id, version]
        else:
            sql = f'SELECT DISTINCT ON (artifact_id) * FROM "{self.table_name}" WHERE artifact_id = $1 ORDER BY artifact_id, version DESC;'                
            values = [artifact_id]
        result = await PGConnectionManager.fetch_one(sql, *values)
        return self.pack_record(dict(result)) if result else None
    
    
    async def execute(self, sql: str, *values: Any) -> Any:
        """Execute a raw query"""
        result = await PGConnectionManager.execute(sql, *values)
        return result
    
    async def fetch(self, sql: str, *values: Any) -> List[MODEL]:
        """Fetch multiple rows from the database."""
        result = await PGConnectionManager.fetch(sql, *values)
        return [self.pack_record(dict(row)) for row in result]
    
    def query(
        self, 
        branch_id: int, 
        turn_id: int | None = None,
        filters: dict[str, Any] | None = None, 
        joins: list[JoinType] | None = None,
        select: SelectFields | None = None,
        **kwargs
    ) -> QuerySet:
        """
        Create a query for this namespace.
        
        Args:
            branch: Optional branch or branch ID to query from            
            
        Returns:
            A query set for this namespace
        """
        # sub_queries = {}
        # joins = joins or []
        # if kwargs:
        #     for k,v in kwargs.items():
        #         if isinstance(v, bool):
        #             relation =self.get_relation(k)
        #             if not relation:
        #                 raise ValueError(f"Relation {k} not found in namespace {self.name}")
        #             # sub_queries[k] = relation.foreign_cls.query().limit(10)
        #             joins.append(
        #                 JoinType(
        #                     primary_table=self.table_name,
        #                     primary_key=k,
        #                     foreign_table=relation.foreign_table,
        #                     foreign_key=relation.foreign_key,
        #                 )
        #             )
        #         elif isinstance(v, PostgresQuerySet):
        #             sub_queries[k] = v
        #         else:
        #             raise ValueError(f"Invalid argument {k} = {v}")
        
        # return PostgresQuerySet(
        #     model_class=self.model_class, 
        #     namespace=self,  
        #     branch_id=branch_id, 
        #     select=select, 
        #     joins=joins, 
        #     filters=filters,
        #     sub_queries=sub_queries
        # )
        return SelectQuerySet(self.model_class).select("*")
        
            
        
        
        
    def partition_query(self, partition_id: int | None = None, branch: int | Branch | None = None, joins: list[NSRelationInfo] | None = None) -> QuerySet:
        """
        Create a query for this namespace.
        """
        return PostgresQuerySet(self.model_class, self, partition_id, branch, joins=joins)