import textwrap
from typing import TYPE_CHECKING, Any, Callable, Dict, Generator, Literal, Type, Optional, List, get_args, get_origin
import uuid
from typing_extensions import TypeVar

from promptview.model2.postgres.operations import JoinType, PostgresOperations, SelectType
from promptview.model2.postgres.query_parser import build_query, build_where_clause
from promptview.model2.query_filters import QueryFilter, QueryProxy, SelectField
from promptview.model2.versioning import ArtifactLog
from promptview.model2.base_namespace import NSRelationInfo, QuerySet, QuerySetSingleAdapter, SelectFields
from promptview.utils.db_connections import PGConnectionManager

from promptview.model2.postgres.fields_query import PgFieldInfo
if TYPE_CHECKING:
    from promptview.model2.postgres.namespace import PostgresNamespace    
    from promptview.model2.model import Model
    
    



        




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



MODEL = TypeVar("MODEL", bound="Model")

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
        # if alias is None:
            # alias = "".join( [w[0] for w in namespace.table_name.split("_")])
        self._alias = alias
        self.namespace = namespace
        self.branch_id = branch_id
        self.filters = filters or {}
        self.filter_proxy = None
        self.limit_value = None
        self.offset_value = None
        self.order_by_value = None
        self.include_fields = None
        self.joins = joins or []
        self._select = select or []
        self.turn_limit_value = None
        self.turn_order_direction = None
        self.sub_queries = sub_queries or {}
        self.parent_query_set = parent_query_set
        self.depth = depth
        self._type = "query"
        self._raw_query = None
        self.cte_target = None

    # @property
    # def q(self) -> QueryProxy[MODEL, PgFieldInfo]:
        # return QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
        
    @property
    def table_name(self) -> str:
        return self.namespace.table_name
    
    
    def _gen_alias(self, index: int | None = None) -> str:
        post_fix = ""
        if self.depth > 0:
            post_fix += str(self.depth)
        if index is not None:
            post_fix += str(index)
        alias = "".join( [w[0] for w in self.namespace.table_name.split("_")])
        return alias + post_fix
        
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
    
    def include(self, *fields: "SelectField | str") -> "PostgresQuerySet[MODEL]":
        """Include a relation field in the query results."""
        if self.include_fields is not None:
            raise ValueError("Include fields already set")
        self.include_fields = []
        for field in fields:
            if isinstance(field, str):
                field_info = self.namespace.get_field(field)
                if field_info is None:
                    raise ValueError(f"Field {field} not found in namespace {self.namespace.name}")
                field = SelectField(field, field_info)            
            self.include_fields.append(field)
        return self
    
    
    
    
    def alias(self, alias: str) -> "PostgresQuerySet[MODEL]":
        """Set the alias for the query"""
        self._alias = alias
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
    
    
    def raw_query(self, sql: str) -> "QuerySet[MODEL]":
        self._raw_query = textwrap.dedent(sql.strip())
        return self
    
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
    
    
    def iter_fields(self) -> Generator[str, None, None]:
        if self.include_fields is None:
            for field in self.namespace.iter_fields():
                if self._alias:
                    yield f'{self._alias}."{field.name}"'
                else:
                    yield f'"{field.name}"'
        else:
            for field in self.include_fields:
                name = field.get()
                if self._alias:
                    yield f'{self._alias}.{name}'
                else:
                    yield name
        # else:
        #     for sf in select:
        #         if sf is dict:
                    
        #         field = self.namespace.get_field(sf)
        #         yield         
        
 
    def build_select_clause(self, alias: str | None = None, select: list[str | dict[str, str]] | None = None) -> str:
        sql = ""
        
        # if self.sub_queries:
        #     sub_queries = []
        #     for idx, (sb_name, sub_query) in enumerate(self.sub_queries.items()):
        #         sq_sql = sub_query.build_query(f"s{sb_name[0]}{idx}")
        #         sub_queries.append(self.wrap_subquery_clause(sq_sql, sb_name))
                
        #     sql += "WITH " + ",\n".join(sub_queries) + "\n"
        alias = alias or self._alias
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
        if self._raw_query is not None:
            return self._raw_query
        # alias = None
        # alias = alias or self.table_name[0]
        alias = alias or self._alias
        if alias is None and self.joins:
            alias = self._gen_alias()
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
            sql += self.build_join_clause(alias)
        
        if self.filter_proxy:
            sql += "WHERE " + self.build_where_clause(self.filter_proxy, alias)
        if self.joins:
            sql += f"GROUP BY {alias}.{self.namespace.primary_key.name}\n"
        
        # if self._type == "cte":
        #     sql += self.build_cte_clause()
        
        return sql
    
    
    def build_cte_clause(self):
        sql = "\nUNION ALL\n\n"
        fields = [f"""b."{field.name}" """ for field in self.namespace.iter_fields()]
        sql += self.wrap_select_clause(
            self.build_fields_clause(*fields), 
            # from_clause=f""" "{self.cte_target.alias}" AS b"""
            from_clause=f""" "{self.cte_target.join.relation.primary_table}" AS b"""
        )
        sql += f"""JOIN "{self.cte_target.query_name}" {self._alias} ON b.id = {self._alias}.{self.cte_target.join.relation.foreign_key}"""
        return sql
    
    def build_cte_query(self):
        if self._raw_query is not None:
            return self._raw_query
        sql = ""
        sql += self.build_select_clause("mb")
        sql += "\nUNION ALL\n\n"
        fields = [f"""b."{field.name}" """ for field in self.namespace.iter_fields()]
        sql += self.wrap_select_clause(
            self.build_fields_clause(*fields), 
            # from_clause=f""" "{self.cte_target.alias}" AS b"""
            from_clause=f""" "{self.cte_target.join.relation.primary_table}" AS b"""
        )
        sql += f"""JOIN "{self.cte_target.query_name}" {self._alias} ON b.id = {self._alias}.{self.cte_target.join.relation.foreign_key}"""
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
        if self._select:
            select_types = [SelectType(namespace=sf["namespace"].name, fields=[f.name for f in sf["fields"]]) for sf in self._select]
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
