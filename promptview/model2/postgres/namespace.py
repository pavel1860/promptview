from enum import Enum
import inspect
import json
import textwrap
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Literal, Type, Optional, List, get_args, get_origin
import uuid
from typing_extensions import TypeVar
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from promptview.model2.postgres.builder import SQLBuilder
from promptview.model2.postgres.operations import JoinType, PostgresOperations, SelectType
from promptview.model2.postgres.query_parser import build_query, build_where_clause
from promptview.model2.query_filters import QueryFilter, QueryProxy, parse_query_params
from promptview.model2.versioning import ArtifactLog, Branch, Turn
from promptview.utils.model_utils import get_list_type, is_list_type, make_json_serializable
from promptview.model2.base_namespace import DatabaseType, NSManyToManyRelationInfo, NSRelationInfo, Namespace, NSFieldInfo, QuerySet, QuerySetSingleAdapter, SelectFields
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt
if TYPE_CHECKING:
    from promptview.model2.namespace_manager import NamespaceManager
    from promptview.model2.model import Model
    
    
PgIndexType = Literal["btree", "hash", "gin", "gist", "spgist", "brin"]



class PgJoin:
    relation: NSRelationInfo
    _index: int | None = None
    depth: int = 0
    def __init__(
        self,
        relation: NSRelationInfo,
        query_set: "PostgresQuerySet",
        depth: int = 0,
    ):
        self.relation = relation
        self._index = None        
        self.query_set = query_set 
        self.depth = depth
    @property
    def index(self) -> int:
        if self._index is None:
            raise ValueError("Join index not set")
        return self._index
    
    @property
    def alias(self) -> str:
        return f"{self.relation.foreign_table[0]}" + str(self.depth) + str(self.index)


class PgCte:
    key: str
    q1_labels: dict[str, str] | None = None
    q2_labels: dict[str, str] | None = None
    def __init__(self, key: str, alias: str, join: PgJoin, q1_labels: dict[str, str] | None = None, q2_labels: dict[str, str] | None = None):
        self.key = key
        self.alias = alias
        self.join = join
        self.q1_labels = q1_labels
        self.q2_labels = q2_labels
        self._query_name = None
        
    def set_query_name(self, query_name: str):
        self._query_name = query_name
        
    @property
    def query_name(self) -> str:
        if self._query_name is None:
            raise ValueError("Query name not set")
        return self._query_name

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
            self.sql_type = self.build_sql_type()
        if extra and "index" in extra:
            self.index = extra["index"]
            
    def serialize(self, value: Any) -> Any:
        """Serialize the value for the database"""
        if self.is_key and self.key_type == "uuid" and value is None:
            value = str(uuid.uuid4())
        elif self.sql_type == "JSONB":
            if self.is_list:
                value = [make_json_serializable(item) if isinstance(item, dict) else item for item in value]
                value = json.dumps(value)
            elif self.field_type is BaseModel:
                value = value.model_dump()
            elif self.data_type is dict:
                value = make_json_serializable(value)
                return json.dumps(value)
                # parsed_values = {}
                # for k, v in value.items():
                #     if isinstance(v, uuid.UUID):
                #         parsed_values[k] = str(v)
                #     elif isinstance(v, dt.datetime):
                #         parsed_values[k] = v.isoformat()
                #     else:
                #         parsed_values[k] = v                                        
                # try:
                #     return json.dumps(parsed_values)
                # except Exception as e:
                #     raise ValueError(f"Failed to serialize dict: {value}") from e
                
                
        return value
    
    def get_placeholder(self, index: int) -> str:
        """Get the placeholder for the value"""
        if self.sql_type == "JSONB":
            if self.is_list:
                return f'${index}::JSONB'
            else:
                return f'${index}::JSONB'
        elif self.is_temporal:
            if self.db_type:
                return f'${index}::{self.db_type}'
            return f'${index}::TIMESTAMP'
        else:
            return f'${index}'
    
    def deserialize(self, value: Any) -> Any:
        """Deserialize the value from the database"""
        if self.is_key and self.key_type == "uuid":
            if type(value) is None:
                raise ValueError("UUID field can not be None")
            return uuid.UUID(str(value))            
        if self.is_list and type(value) is str:
            return json.loads(value)
        elif self.data_type is dict:
            return json.loads(value)
        elif self.data_type is BaseModel:
            return self.data_type.model_validate_json(value)
        elif self.is_enum and not self.is_literal:
            return self.data_type(value)
        return value
            
    
    def build_sql_type(self) -> str:
        sql_type = None
        
        # if inspect.isclass(self.data_type):
        #     if issubclass(self.data_type, BaseModel):
        #         sql_type = "JSONB"
        #     elif issubclass(self.data_type, Enum):
        #         sql_type = "TEXT" 
        if self.db_type:
            sql_type = self.db_type               
        elif self.is_temporal:
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
        elif self.data_type is uuid.UUID:
            sql_type = "UUID[]" if self.is_list else "UUID"
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
        alias: str | None = None,
        branch_id: int | None = None, 
        joins: list[PgJoin] | None = None,
        filters: dict[str, Any] | None = None,
        select: list[list[SelectFields]] | None = None,
        sub_queries: dict[str, Any] | None = None,
        parent_query_set: "PostgresQuerySet | None" = None,
        depth: int = 0,
    ):
        super().__init__(model_class=model_class)
        if alias is None:
            alias = "".join( [w[0] for w in namespace.table_name.split("_")])
        self.alias = alias
        self.namespace = namespace
        self.branch_id = branch_id
        self.filters = filters or {}
        self.filter_proxy = None
        self.limit_value = None
        self.offset_value = None
        self.order_by_value = None
        self.include_fields = None
        self.joins = joins or []
        self.select = select or []
        self.turn_limit_value = None
        self.turn_order_direction = None
        self.sub_queries = sub_queries or {}
        self.parent_query_set = parent_query_set
        self.depth = depth
        self._type = "query"
        # self.cte_target = None

    # @property
    # def q(self) -> QueryProxy[MODEL, PgFieldInfo]:
        # return QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
        
    @property
    def table_name(self) -> str:
        return self.namespace.table_name
        
    def filter(self, filter_fn: Callable[[MODEL], bool] | None = None, **kwargs) -> "PostgresQuerySet[MODEL]":
        """Filter the query"""
        self.filters.update(kwargs)            
        if filter_fn is not None:
            proxy = QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
            self.filter_proxy = filter_fn(proxy)    
        return self
    
    def set_filter(self, query_filter: QueryFilter) -> "PostgresQuerySet[MODEL]":
        self.filter_proxy = query_filter
        return self
    
    def limit(self, limit: int) -> "PostgresQuerySet[MODEL]":
        """Limit the query results"""
        self.limit_value = limit
        return self
    
    def order_by(self, field: str, direction: Literal["asc", "desc"] = "asc") -> "PostgresQuerySet[MODEL]":
        """Order the query results"""
        self.order_by_value = f"{field} {direction}"
        return self
    
    def turn_limit(self, limit: int, order_direction: Literal["asc", "desc"] = "desc") -> "PostgresQuerySet[MODEL]":
        """Limit the query results to the last N turns"""
        self.turn_limit_value = limit
        self.turn_order_direction = order_direction
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
    
    def tail(self, limit: int = 10) -> "QuerySet[MODEL]":
        """Get the last N results"""
        self.limit_value = limit
        self.order_by_value = "created_at desc"
        return self
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        """Get the first result"""
        self.limit_value = 1
        self.order_by_value = "created_at asc"
        return QuerySetSingleAdapter(self)
    
    def head(self, limit: int = 10) -> "QuerySet[MODEL]":
        """Get the first N results"""
        self.limit_value = limit
        self.order_by_value = "created_at asc"
        return self
    
    def include(self, fields: list[str]) -> "PostgresQuerySet[MODEL]":
        """Include a relation field in the query results."""
        self.include_fields = fields
        return self
    
    
    
    def sub_query(self, query_set: "PostgresQuerySet", name: str | None = None) -> "PostgresQuerySet[MODEL]":
        """Create a sub query"""
        if name is None:
            name = query_set.namespace.table_name + "_sb"
            
        if query_set.cte_target is not None:
            query_set.cte_target.set_query_name(name)
        # query_set.alias = name[0:2]
        self.sub_queries[name] = query_set
        return self
    
    def cte(self, alias: str, key: str, q1_labels: dict[str, str] | None = None, q2_labels: dict[str, str] | None = None):
        """Create a common table expression"""
        self._type = "cte"
        relation = self.namespace.get_relation_by_type(self.model_class)
        query_set = PostgresQuerySet(relation.foreign_cls, relation.foreign_namespace, parent_query_set=self, depth=self.depth+1)
        join = PgJoin(relation, query_set, self.depth+1)
        self.cte_target = PgCte(key, alias, join, q1_labels, q2_labels)
        # self.join(self.model_class)
        return self
    
    # def join(self, model: "Type[Model]") -> "PostgresQuerySet[MODEL]":
    #     """Join the query with another model"""
    #     relation = self.namespace.get_relation_by_type(model)
    #     if not relation:
    #         raise ValueError(f"Relation {model} not found in namespace {self.namespace.name}")
        
    #     query_set = PostgresQuerySet(relation.foreign_cls, relation.foreign_namespace, parent_query_set=self, depth=self.depth+1)
    #     join = self._add_join(PgJoin(relation, query_set, self.depth+1))
    #     return join.query_set
    
    def join(self, *models: "Type[Model]") -> "QuerySet[MODEL]":
        """Join the query with another model"""
        prev_query_set = self
        
        for model in models:
            relation = prev_query_set.namespace.get_relation_by_type(model)
            if not relation:
                raise ValueError(f"Relation {model} not found in namespace {self.namespace.name}")        
            query_set = PostgresQuerySet(relation.foreign_cls, relation.foreign_namespace, parent_query_set=self, depth=self.depth+1)
            join = prev_query_set._add_join(PgJoin(relation, query_set, prev_query_set.depth+1))            
            prev_query_set = query_set
        return self
    
    def _add_join(self, join: PgJoin):
        join._index = len(self.joins)
        self.joins.append(join)
        return join
    
    # def build_subquery2(self, name: str):        
    #     sub_queries = []
    #     for sb_name, sub_query in self.sub_queries.items():
    #         sub_queries += sub_query.build_subquery(sb_name)
        
    #     sql = f"{name}_subquery AS (\n"
    #     sql += textwrap.indent(self.build_query(name), "    ")
    #     sql += "\n)"
    #     sub_queries.append(sql)
    #     return sub_queries
    
    # def build_subquery3(self, name: str):
    #     sql_list = []        
    #     for sb_name, sub_query in self.sub_queries.items():
    #         sql, values = build_query(
    #             sub_query.namespace,
    #             filters=sub_query.filters,
    #             limit=sub_query.limit_value,
    #             order_by=sub_query.order_by_value,
    #             offset=sub_query.offset_value,
    #             # select=select_types,
    #             # joins=self.joins,
    #             alias="t",
    #             start_placeholder=len(sql_list[-1][1]) if sql_list else 0,
    #             filter_proxy=sub_query.filter_proxy,
    #         )
    #         sub_sql = f"{name}_subquery AS (\n"
    #         sub_sql += textwrap.indent(sql, "    ")
    #         sub_sql += "\n)"
    #         sql_list.append((sub_sql, values))
    #     return sql_list
    
    
    # def build_join_select_clause(self, alias: str, as_alias: str | None = None) -> str:
    #     sql = (
    #        "COALESCE(\n" 
    #        "\tjson_agg(\n"
    #        "\t\tDISTINCT jsonb_build_object(\n"
    #     )
        
    #     for field in self.namespace.iter_fields():
    #         sql += f"\t\t\t'{field.name}', {alias}.{field.name}, \n"
    #     for join in self.joins:
    #         join_sql = join.query_set.build_join_select_clause(join.alias, as_alias=join.relation.name)
    #         sql += textwrap.indent(join_sql, "\t")
    #     sql = sql.rstrip(", \n") + "\n"
    #     sql += (
    #         f"\t\t)\n"
    #         f"\t) FILTER (WHERE {alias}.{self.namespace.primary_key.name} IS NOT NULL),\n"
    #         "\t'[]'\n"
    #     )
    #     if as_alias:
    #         sql += f") AS {as_alias}\n"
    #     else:
    #         sql += ")\n"
    #     return sql
    
    def add_json_agg(self, sql: str, filter_clause: str | None = None):
        new_sql = "json_agg(\n"
        new_sql += textwrap.indent(sql, "   ")
        if filter_clause:
            new_sql += f") FILTER (WHERE {filter_clause})\n"
        else:
            new_sql += ")\n"
        return new_sql
    
    def add_jsonb_build_object(self, sql: str, distinct: bool = False):
        new_sql = "jsonb_build_object(\n"
        if distinct:
            new_sql = "DISTINCT " + new_sql
        new_sql += textwrap.indent(sql, "   ")
        new_sql += ")\n"
        return new_sql
            
        
    def add_coalesce(self, sql: str, default_value: str = "'[]'", as_alias: str | None = None):
        new_sql = "COALESCE(\n"
        new_sql += textwrap.indent(sql, "   ")
        new_sql += f", {default_value}\n"        
        if as_alias:
            new_sql += f") AS {as_alias}\n"
        else:
            new_sql += ")\n"
        return new_sql
    
    def wrap_select_clause(self, sql: str, from_clause: str, where_clause: str | None = None):
        new_sql = f"SELECT\n"
        new_sql += textwrap.indent(sql, "   ")
        new_sql += f"FROM {from_clause}\n"
        if where_clause:
            new_sql += f"WHERE {where_clause}\n"
        return new_sql

    def list_fields_clause(self, alias: str | None = None) -> list[str]:
        if alias is None:
            return [f""" "{field.name}" """ for field in self.namespace.iter_fields()]
        return [f"""'{field.name}', {alias}."{field.name}" """ for field in self.namespace.iter_fields()]
    
    # def build_nested_join_select_clause(self, name: str, parent_alias: str, alias: str) -> str:
    #     sql = ""
    #     fields = self.list_fields_clause(alias)
    #     for join in self.joins:
    #         join_sql = join.query_set.build_nested_join_select_clause(join.relation.name, alias, join.alias)
    #         fields.append(join_sql)
    #     sql = self.build_fields_clause(*fields)
    #     sql = self.add_jsonb_build_object(sql, distinct=False)
    #     sql = self.add_json_agg(sql)
    #     sql = self.wrap_select_clause(
    #         sql, 
    #         from_clause=f""" "{self.namespace.table_name}" {alias}""", 
    #         where_clause=f"{alias}.{self.namespace.primary_key.name}={parent_alias}.{self.namespace.primary_key.name}"
    #         )
    #     sql = "(\n" + textwrap.indent(sql, "    ") + "\n)"
    #     sql = self.add_coalesce(sql, default_value="'[]'")
    #     sql = f"'{name}', {sql}"
    #     return sql
    
        
    # def build_join_select_clause(self, name: str, alias: str, as_alias: str | None = None) -> str:        
    #     sql = ""

    #     fields = self.list_fields_clause(alias)
    #     for join in self.joins:
    #         join_sql = join.query_set.build_nested_join_select_clause(join.relation.name, alias, join.alias)
    #         fields.append(join_sql)
        
    #     sql = self.build_fields_clause(*fields)        
    #     sql = self.add_jsonb_build_object(sql, distinct=True)
    #     sql = self.add_json_agg(sql, filter_clause=f"{alias}.{self.namespace.primary_key.name} IS NOT NULL")
    #     sql = self.add_coalesce(sql, default_value="'[]'")
    #     sql = sql.rstrip(", \n")
    #     sql = sql + f" AS {name} \n"
    #     return sql
    
    
    def build_nested_join_select_clause(self, join: PgJoin, parent_alias: str) -> str:
        sql = ""
        fields = self.list_fields_clause(join.alias)
        for sub_join in self.joins:
            join_sql = sub_join.query_set.build_nested_join_select_clause(sub_join, join.alias)
            fields.append(join_sql)
        sql = self.build_fields_clause(*fields)
        sql = self.add_jsonb_build_object(sql, distinct=False)
        sql = self.add_json_agg(sql)
        sql = self.wrap_select_clause(
            sql, 
            from_clause=f""" "{self.namespace.table_name}" {join.alias}""", 
            where_clause=f"{join.alias}.{join.relation.foreign_key}={parent_alias}.{join.relation.primary_key}"
            )
        sql = "(\n" + textwrap.indent(sql, "    ") + "\n)"
        sql = self.add_coalesce(sql, default_value="'[]'")
        sql = f"'{join.relation.name}', {sql}"
        return sql


    def build_join_select_clause(self, join: PgJoin) -> str:        
        sql = ""

        fields = self.list_fields_clause(join.alias)
        for sub_join in self.joins:
            join_sql = sub_join.query_set.build_nested_join_select_clause(sub_join, join.alias)
            fields.append(join_sql)
        
        sql = self.build_fields_clause(*fields)        
        sql = self.add_jsonb_build_object(sql, distinct=True)
        sql = self.add_json_agg(sql, filter_clause=f"""{join.alias}."{self.namespace.primary_key.name}" IS NOT NULL""")
        sql = self.add_coalesce(sql, default_value="'[]'")
        sql = sql.rstrip(", \n")
        sql = sql + f" AS {join.relation.name} \n"
        return sql

    
    
    def get_joins(self) -> Generator[PgJoin, None, None]:        
        for join in self.joins:
            yield join
            yield from join.query_set.get_joins()
    
    def build_join_clause(self, alias: str) -> str:
        sql = ""
        qs = self
        for join in self.get_joins():
            # sql += f"""JOIN "{join.relation.foreign_table}" AS {join.alias} ON {join.alias}.{join.relation.foreign_key} = {alias}.{self.namespace.primary_key.name}\n"""
            sql += f"""JOIN "{join.relation.foreign_table}" AS {join.alias} ON {join.alias}.{join.relation.foreign_key} = {alias}.{qs.namespace.primary_key.name}\n"""
            alias = join.alias
            qs = join.query_set
        for idx, (sb_name, sub_query) in enumerate(self.sub_queries.items()):
            sb_alias = f"{sb_name[0]}{idx}s"
            sql += f"""JOIN {sb_name} AS {sb_alias} ON {sb_alias}.{sub_query.namespace.primary_key.name} = {alias}.{self.namespace.primary_key.name}\n"""
        return sql
    
 
    
    def build_fields_clause(self, *fields: str) -> str:
        return ",\n".join(fields) + "\n"
    
    
    def wrap_subquery_clause(self, sql: str, name: str) -> str:
        sq_sql = f"{name} AS (\n"
        sq_sql += textwrap.indent(sql, "  ")
        sq_sql += "\n)"
        return sq_sql
    
    
    def iter_fields(self, select: list[str | dict[str, str]] | None = None) -> Generator[PgFieldInfo, None, None]:
        if select is None:
            for field in self.namespace.iter_fields():
                yield field
        else:
            for field in select:
                yield field
 
    def build_select_clause(self, alias: str | None = None, select: list[str | dict[str, str]] | None = None) -> str:
        sql = ""
        
        # if self.sub_queries:
        #     sub_queries = []
        #     for idx, (sb_name, sub_query) in enumerate(self.sub_queries.items()):
        #         sq_sql = sub_query.build_query(f"s{sb_name[0]}{idx}")
        #         sub_queries.append(self.wrap_subquery_clause(sq_sql, sb_name))
                
        #     sql += "WITH " + ",\n".join(sub_queries) + "\n"
        alias = alias or self.alias
        if alias:
            sql += f'SELECT \n'
            fields = [f"""{alias}."{field.name}" """ for field in self.namespace.iter_fields()]            
            for join in self.joins:                
                join_sql = join.query_set.build_join_select_clause(join)
                fields.append(join_sql)                
            sql += textwrap.indent(self.build_fields_clause(*fields), "  ")
            sql += f'FROM "{self.namespace.table_name}" AS {alias}\n'        
        else:
            sql = f'SELECT *\n'
            sql += f'FROM "{self.namespace.table_name}"\n'        
        
        return sql
    

    def build_where_clause(self, filter_proxy: QueryProxy[MODEL, PgFieldInfo], alias: str | None = None) -> str:
       return build_where_clause(filter_proxy, alias) + "\n"
       
    
    def build_query(self, alias: str | None = None):
        # alias = None
        # alias = alias or self.table_name[0]
        alias = alias or self.alias
        sql = ""
        if self.sub_queries:
            sub_queries = []
            sub_query_clause = "WITH "
            for idx, (sb_name, sub_query) in enumerate(self.sub_queries.items()):
                if sub_query._type == "cte":
                    sq_sql = sub_query.build_cte_query()
                    sub_query_clause += "RECURSIVE "
                    # sb_name = sub_query.cte_target.alias
                else:
                    sq_sql = sub_query.build_query(f"s{sb_name[0]}{idx}")
                sub_queries.append(self.wrap_subquery_clause(sq_sql, sb_name))
                
            sql += sub_query_clause + ",\n".join(sub_queries) + "\n"
            
        sql += self.build_select_clause(alias)
        if self.joins or self.sub_queries:
            sql += self.build_join_clause(self.alias)
        
        if self.filter_proxy:
            sql += "WHERE " + self.build_where_clause(self.filter_proxy, alias)
        if self.joins:
            sql += f"GROUP BY {alias}.{self.namespace.primary_key.name}\n"
        
        if self._type == "cte":
            sql += self.build_cte_clause()
        
        return sql
    
    
    def build_cte_clause(self):
        sql = "\nUNION ALL\n\n"
        fields = [f"""b."{field.name}" """ for field in self.namespace.iter_fields()]
        sql += self.wrap_select_clause(
            self.build_fields_clause(*fields), 
            # from_clause=f""" "{self.cte_target.alias}" AS b"""
            from_clause=f""" "{self.cte_target.join.relation.primary_table}" AS b"""
        )
        sql += f"""JOIN "{self.cte_target.query_name}" {self.alias} ON b.id = {self.alias}.{self.cte_target.join.relation.foreign_key}"""
        return sql
    
    def build_cte_query(self):
        sql = ""
        sql += self.build_select_clause("mb")
        sql += "\nUNION ALL\n\n"
        fields = [f"""b."{field.name}" """ for field in self.namespace.iter_fields()]
        sql += self.wrap_select_clause(
            self.build_fields_clause(*fields), 
            # from_clause=f""" "{self.cte_target.alias}" AS b"""
            from_clause=f""" "{self.cte_target.join.relation.primary_table}" AS b"""
        )
        sql += f"""JOIN "{self.cte_target.query_name}" {self.alias} ON b.id = {self.alias}.{self.cte_target.join.relation.foreign_key}"""
        return sql
    ##########################
    
    def build_subquery(self, name: str, start_idx: int=0, joins: list[JoinType] | None = None, alias: str | None = None):
        joins = joins or []
        sql, values = build_query(
            self.namespace,
            filters=self.filters,
            limit=self.limit_value,
            order_by=self.order_by_value,
            offset=self.offset_value,
            # select=select_types,
            joins=self.joins + joins,
            alias=alias,
            start_placeholder=start_idx,
            filter_proxy=self.filter_proxy,
        )
        
        sub_sql = f"{name} AS (\n"
        sub_sql += textwrap.indent(sql, "    ")
        sub_sql += "\n)"
        return (sub_sql, values, name, start_idx + len(values))
    
    
    def flat_subqueries(self) -> list["PostgresQuerySet"]:
        sub_queries = []
        for sb_name, sub_query in self.sub_queries.items():
            sub_queries += sub_query.flat_subqueries() + [sub_query]
        return sub_queries
    
    def build_all_subqueries(self) -> list[tuple[str, list[Any], str, int, "PostgresQuerySet"]]:
        query_list = self.flat_subqueries()
        start_idx = 0
        queries = []
        for idx, qs in enumerate(query_list):
            joins = None
            alias = f"{qs.table_name[0]}{idx}"
            if idx > 0:
                prev_qs = query_list[idx-1]
                joins = [{
                    "primary_table": alias,
                    "primary_key": qs.namespace.primary_key.name,
                    "foreign_table": queries[idx-1][2],
                    "foreign_key": qs.namespace.get_relation(prev_qs.namespace.table_name).foreign_key,
                }]
                # joins = qs.namespace.get_relation_joins(prev_qs.namespace.table_name, primary_alias=alias)
            sql, values, name, start_idx = qs.build_subquery(f"{qs.table_name}_sq_{idx}", start_idx=start_idx, joins=joins, alias=alias)
            queries.append((sql, values, name, start_idx, qs))
        return queries
    
    
    
    # def build_all_subqueries(self):
    #     sub_queries = []
    #     start_idx = 0
    #     for sb_name, sub_query in self.sub_queries.items():
    #         sub_queries += sub_query.build_all_subqueries()
    #         if sub_queries:
    #             start_idx = sub_queries[-1][3]
    #         sql, values, name, start_idx = sub_query.build_subquery(sb_name, start_idx=start_idx)
    #         sub_queries.append((sql, values, name, start_idx))
            
    #     return sub_queries


    def build_query2(self, with_subqueries: bool = False):
        start_idx = 0
        sub_queries = []
        sq_values = []
        joins = []
        sq_sql = ""
        alias = self.table_name[0]
        if with_subqueries:
            sub_queries = self.build_all_subqueries()
            if sub_queries:
                start_idx = sub_queries[-1][3]
                if sub_queries:
                    sq_sql = ",\n".join([sq[0] for sq in sub_queries]) + "\n"
                    sq_values = [v for sq in sub_queries for v in sq[1]]
                    # sql += f"\nJOIN ({sql}) t ON t.id = {self.namespace.table_name}.id\n"        
                    sq_sql = "WITH " + sq_sql
                    joins = [{
                        "primary_table": alias,
                        "primary_key": self.namespace.primary_key.name,
                        "foreign_table": sub_queries[-1][2],
                        "foreign_key": self.namespace.get_relation(sub_queries[-1][4].table_name).foreign_key,
                    }]
                # joins = self.namespace.get_relation_joins(sub_queries[-1][4].namespace.table_name, primary_alias=alias)
        
        sql, values = build_query(
            self.namespace,
            filters=self.filters,
            limit=self.limit_value,
            order_by=self.order_by_value,
            offset=self.offset_value,
            # select=select_types,
            joins=self.joins + joins,
            filter_proxy=self.filter_proxy,
            start_placeholder=start_idx,
            alias=alias,
        )

        if sub_queries:
            sql = sq_sql + "\n" + sql
            values = sq_values + values
        
        return sql, values
    
    def root_query_set(self) -> "PostgresQuerySet":
        ex_query = self
        while ex_query.parent_query_set:
            ex_query = ex_query.parent_query_set
        return ex_query

    
    async def execute(self) -> List[MODEL]:
        ex_query = self.root_query_set()
        sql = ex_query.build_query()
        results = await PGConnectionManager.fetch(sql)        
        return [ex_query.model_class(**ex_query.pack_record(dict(result))) for result in results]
    
    
    
    async def execute2(self) -> List[MODEL]:
        """Execute the query"""
        # Use PostgresOperations to execute the query with versioning support
        if self.select:
            select_types = [SelectType(namespace=sf["namespace"].name, fields=[f.name for f in sf["fields"]]) for sf in self.select]
        else:
            select_types = None
        # partition_id, branch_id = await self.namespace.get_current_ctx_partition_branch(partition=self.partition_id, branch=self.branch_id)
        sql, values = build_query(
            self.namespace,
            filters=self.filters,
            limit=self.limit_value,
            order_by=self.order_by_value,
            offset=self.offset_value,
            select=select_types,
            joins=self.joins,
            filter_proxy=self.filter_proxy,
        )
        
        if self.namespace.is_versioned:
            results = await ArtifactLog.fetch(
                table_name=self.namespace.table_name,
                sql=sql,
                values=values,
                branch_id=self.branch_id or 1,
                turn_limit=self.turn_limit_value,
                turn_direction=self.turn_order_direction,
                is_event_source=True,
            )
        else:
            results = await PGConnectionManager.fetch(sql, *values)
        
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
        
        sql = f"""
        INSERT INTO "{self.table_name}" ({", ".join(keys)})
        VALUES ({", ".join(placeholders)})
        RETURNING *;
        """
        return sql, values
    
    
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

        sql = f"""
        UPDATE "{self.table_name}"
        SET {", ".join(set_parts)}
        WHERE {self.primary_key.name} = ${len(values)}
        RETURNING *;
        """
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
    
    async def save(self, model: MODEL) -> MODEL:
        """
        Save data to the namespace.
        
        Args:
            model: The model to save
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
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
    
    
    
    def query(
        self, 
        branch: int | Branch | None = None, 
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
        # branch = self.get_current_ctx_branch(branch) if self.is_versioned else None
        # partition, branch = self.get_current_ctx_partition_branch(partition=partition_id, branch=branch)
        # if kwargs:
        #     joins = joins or []
        #     for k,v in kwargs.items():
        #         joins.append(
        #             JoinType(
        #                 primary_table=self.table_name,
        #                 primary_key=k,
        #                 foreign_table=v.namespace.table_name,
        #                 foreign_key=v.namespace.primary_key.name,
        #             )
        #         )
        sub_queries = {}
        joins = joins or []
        if kwargs:
            for k,v in kwargs.items():
                if isinstance(v, bool):
                    relation =self.get_relation(k)
                    if not relation:
                        raise ValueError(f"Relation {k} not found in namespace {self.name}")
                    # sub_queries[k] = relation.foreign_cls.query().limit(10)
                    joins.append(
                        JoinType(
                            primary_table=self.table_name,
                            primary_key=k,
                            foreign_table=relation.foreign_table,
                            foreign_key=relation.foreign_key,
                        )
                    )
                elif isinstance(v, PostgresQuerySet):
                    sub_queries[k] = v
                else:
                    raise ValueError(f"Invalid argument {k} = {v}")
        
        return PostgresQuerySet(
            model_class=self.model_class, 
            namespace=self,  
            branch_id=branch, 
            select=select, 
            joins=joins, 
            filters=filters,
            sub_queries=sub_queries
        )
        
            
        
        
        
    def partition_query(self, partition_id: int | None = None, branch: int | Branch | None = None, joins: list[NSRelationInfo] | None = None) -> QuerySet:
        """
        Create a query for this namespace.
        """
        return PostgresQuerySet(self.model_class, self, partition_id, branch, joins=joins)