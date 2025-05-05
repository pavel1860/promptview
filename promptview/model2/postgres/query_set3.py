









from typing import TYPE_CHECKING, Any, Callable, Generator, Generic, List, Literal, Self, Type
from typing_extensions import TypeVar

from promptview.model2.base_namespace import Namespace, NSRelationInfo

from promptview.model2.postgres.fields_query import PgFieldInfo
# from promptview.model2.query_filters import QueryProxy
from promptview.model2.postgres.sql.helpers import NestedQuery
from promptview.utils.db_connections import PGConnectionManager


from promptview.model2.postgres.sql.queries import SelectQuery, Table, Column, Subquery
from promptview.model2.postgres.sql.expressions import Eq, IsNull, Not, RawSQL, Value, Function, Coalesce, Gt, json_build_object, param, OrderBy
from promptview.model2.postgres.sql.compiler import Compiler
from functools import reduce
from operator import and_



# Your ORM interfaces
if TYPE_CHECKING:
    from promptview.model2.model import Model

class QueryWrapper:
    def __init__(self, query: SelectQuery, type: Literal["select", "join_nested", "join_first"]):
        self.query = query
        self.type = type

    

MODEL = TypeVar("MODEL", bound="Model")

T_co = TypeVar("T_co", covariant=True)

class QuerySetSingleAdapter(Generic[T_co]):
    def __init__(self, queryset: "SelectQuerySet[T_co]"):
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



class QueryProxy:
    def __init__(self, model_class, table: Table):
        self.model_class = model_class
        self.table = table
        # self.table.alias = model_class.get_namespace().table_alias  # or pass in if needed

    def __getattr__(self, field_name):
        return Column(field_name, self.table)


def wrap_query_in_json_agg(query: SelectQuery, alias: str, pk_col: Column) -> Coalesce:
    obj = json_build_object(**{col.name: col for col in query.columns})
    agg = Function(
        "json_agg",
        obj,
        distinct=True,
        filter_where=Not(IsNull(pk_col))
    )
    return Coalesce(agg, Value("[]", inline=True), alias=alias)

# def embed_query_as_subquery(outer_query: SelectQuery, inner_query: SelectQuery, alias: str):
#     subquery = Subquery(inner_query, alias=alias)
#     outer_query.from_table = subquery
#     return outer_query


def embed_query_as_subquery(query, rel, parent_table):
        obj = json_build_object(**{
            c.name: c for c in query.columns
        })
        subq = SelectQuery()
        subq.columns = [Function("json_agg", obj)]
        subq.from_table = query.from_table
        subq.joins = query.joins
        # subq.where_clause = self.query.where_clause
        subq.where_clause = Eq(Column(rel.foreign_key, query.from_table), Column(rel.primary_key, parent_table))
        coalesced = Coalesce(subq, Value("[]", inline=True))
        return coalesced

 
class SelectQuerySet(Generic[MODEL]):
    def __init__(self, model_class: Type[MODEL]):
        self.model_class = model_class
        self.alias_lookup = {}

        self.table = Table(model_class.get_namespace().table_name)
        self.table.alias = self._set_alias(self.table.name)
        self.query = SelectQuery().from_(self.table)
        self.query_stack = [self.query]
        self.model_stack = [model_class]
        self.table_stack = [self.table]
        self._params = []

    def _set_alias(self, name: str) -> str:
        base = name[0].lower()
        alias = base
        for i in range(10):
            if alias not in self.alias_lookup:
                break
            alias = f"{base}{i}"
        self.alias_lookup[alias] = name
        return alias
    
    
    def __await__(self):
        return self.execute().__await__()

    @property
    def namespace(self) -> Namespace[MODEL, PgFieldInfo]:
        return self.model_class.get_namespace()
    
    @property
    def curr_query(self):
        return self.query_stack[-1]
    
    @curr_query.setter
    def curr_query(self, query: SelectQuery):
        self.query_stack.append(query)
        
    @property
    def curr_model(self):
        return self.model_stack[-1]
    
    @curr_model.setter
    def curr_model(self, model: Type["Model"]):
        self.model_stack.append(model)
        
    @property
    def query_depth(self):
        return len(self.query_stack)
    
    @property
    def curr_table(self):
        return self.table_stack[-1]
    
    @curr_table.setter
    def curr_table(self, table: Table):
        self.table_stack.append(table)

    # def select(self, *fields: str) -> "SelectQuerySet[MODEL]":
    #     if len(fields) == 1 and fields[0] == "*":
    #         self.curr_query.select(*[Column(f.name, self.curr_table) for f in self.curr_model.iter_fields()])
    #     else:
    #         self.curr_query.select(*[Column(f, self.curr_table) for f in fields])
    #     return self
    
    def select(self, *fields: str) -> "SelectQuerySet[MODEL]":
                
        if len(fields) == 1 and fields[0] == "*":
            self.curr_query.select(*[Column(f.name, self.curr_table) for f in self.curr_model.iter_fields()])
        else:
            self.curr_query.select(*[Column(f, self.curr_table) for f in fields])
        return self
    

    def where(self, condition: Callable[[MODEL], Any] | None = None, **kwargs) -> "SelectQuerySet[MODEL]":
        expressions = []

        if condition is not None:
            proxy = QueryProxy(self.model_class, self.curr_table)
            self.query.where(condition(proxy))
        if kwargs:
            for field, value in kwargs.items():
                col = Column(field, self.curr_table)
                expressions.append(Eq(col, param(value)))
                
        if expressions:
            expr = reduce(and_, expressions) if len(expressions) > 1 else expressions[0]
            self.query.where(expr)

        return self
    
    
    def filter(self, condition: Callable[[MODEL], Any] | None = None, **kwargs) -> "SelectQuerySet[MODEL]":
        return self.where(condition, **kwargs)
    
    def _get_query_set(self, target: "SelectQuerySet | Type[Model]") -> "SelectQuerySet":
        if isinstance(target, SelectQuerySet):
            query_set = target
        else:
            query_set = SelectQuerySet(target).select("*")
        self._gen_query_set_alias(query_set)
        return query_set
        
        
    def _gen_query_set_alias(self, query: "SelectQuerySet"):
        if not query.query.from_table:
            raise ValueError("Query set has no from table")
        query.query.from_table.alias = self._set_alias(query.query.from_table.name)
        return query
    
    def with_cte(self, name: str, query: "SelectQuery | SelectQuerySet | RawSQL", recursive: bool = False):
        if isinstance(query, SelectQuerySet):
            if query.query.ctes:
                # move nested cte to the top level
                self.query.ctes = query.query.ctes + self.query.ctes
                if query.query.recursive:
                    query.query.recursive = False
                    self.query.recursive = True
                query.query.ctes = []
        if hasattr(query, "query"):  # If it's a SelectQuerySet
            query = query.query
            
        self.query.with_cte(name, query, recursive=recursive)    
        return self
    
    
    def join_cte(self, cte_name: str, on_left: str, on_right: str, alias=None):
        """
        Join a Common Table Expression (CTE) to the current query.

        Args:
            cte_name (str): Name of the CTE to join with
            on_left (str): Column name from the current table to use in the join condition
            on_right (str): Column name from the CTE to use in the join condition 
            alias (str, optional): Alias to give the CTE in the join. Defaults to None.

        Returns:
            SelectQuerySet[MODEL]: Returns self for method chaining

        Example:
            query.with_cte("my_cte", subquery) \
                .join_cte("my_cte", "id", "parent_id")
        """
        cte_table = Table(cte_name, alias=alias)
        self.curr_query.join(
            cte_table,
            Eq(Column(on_left, self.curr_table), Column(on_right, cte_table))
        )
        return self
    
    
    def join(self, target: "SelectQuerySet | Type[Model]") -> "SelectQuerySet[MODEL]":
        query_set = self._get_query_set(target)
        rel = self.curr_model.get_namespace().get_relation_by_type(query_set.model_class)
        if rel is None:
            raise ValueError("No relation found")
        
        # if query_set.query.ctes:
        #     self.query.ctes = query_set.query.ctes + self.query.ctes
        #     query_set.query.ctes = []
        
        self.curr_query.join(
            query_set.curr_table, 
            Eq(
                Column(rel.primary_key, self.curr_table), 
                Column(rel.foreign_key, query_set.curr_table)
            )
        )        
        nested_query = embed_query_as_subquery(query_set.query, rel, self.curr_table)    
        self.query.columns.append(nested_query)
        if not self.query.group_by:
            pk = self.model_class.get_namespace().primary_key.name
            p_id = Column(pk, self.table)
            self.query.group_by = [p_id] 
        return self
      
    # def join(self, target: "SelectQuerySet | Type[Model]") -> "SelectQuerySet[MODEL]":
    #     query_set = self._get_query_set(target)
    #     rel = self.curr_model.get_namespace().get_relation_by_type(query_set.model_class)
    #     if rel is None:
    #         raise ValueError("No relation found")
        
    #     if query_set.query.ctes:
    #         self.query.ctes = query_set.query.ctes + self.query.ctes
    #         query_set.query.ctes = []
        
    #     self.curr_query.join(
    #         query_set.curr_table, 
    #         Eq(
    #             Column(rel.primary_key, self.curr_table), 
    #             Column(rel.foreign_key, query_set.curr_table)
    #         )
    #     )
    #     nested_query = NestedQuery(query_set, rel.name, Column(rel.primary_key, self.curr_table), self, self.curr_table, rel)        
    #     nested_query.update_depth()
    #     self.query.columns.append(nested_query)
    #     # self.query.columns.append(Column(rel.name, subquery, alias=rel.name))
    #     if not self.query.group_by:
    #         pk = self.model_class.get_namespace().primary_key.name
    #         p_id = Column(pk, self.table)
    #         self.query.group_by = [p_id] 
    #     return self
        
        

    def join_old(self, related_model: "Type[Model]") -> "SelectQuerySet[MODEL]":
        rel = self.curr_model.get_namespace().get_relation_by_type(related_model)
        if rel is None:
            raise ValueError("No relation found")
        
        ns = related_model.get_namespace()
        related_table = Table(ns.table_name)
        related_table.alias = self._set_alias(related_table.name)

        join_condition = Eq(
            Column(rel.primary_key, self.curr_table),
            Column(rel.foreign_key, related_table)
        )

        self.query.join(related_table, join_condition)
        if self.query_depth == 1:
            self._join_first_table(related_model, related_table, rel)
        else:
            self._join_nested_table(related_model, related_table, rel)
        
        
        if not self.query.group_by:
            pk = self.model_class.get_namespace().primary_key.name
            p_id = Column(pk, self.table)
            self.query.group_by = [p_id] 

        return self
    
    def _join_first_table(self, related_model: "Type[Model]", related_table: Table, rel: NSRelationInfo):
        
        # Add JSON aggregation
        json_obj = json_build_object(**{
            f.name: Column(f.name, related_table) for f in related_model.iter_fields()
        })

        m_id = Column(rel.primary_key, related_table)
        nested_agg = Function(
            "json_agg", json_obj,
            distinct=True,
            filter_where=Not(IsNull(m_id))  # add real filter if needed
        )

        nested = Coalesce(nested_agg, Value("[]"), alias=rel.name)
        self.query.columns.append(nested)
        
        self.curr_query = json_obj
        self.curr_model = related_model
        self.curr_table = related_table
            
    def _join_nested_table(self, related_model: "Type[Model]", related_table: Table, rel: NSRelationInfo):                
        json_obj = json_build_object(**{
            f.name: Column(f.name, related_table) for f in related_model.iter_fields()
        })
        p_id = Column(rel.primary_key, self.curr_table)
        r_id = Column(rel.primary_key, related_table)

        subq = SelectQuery()
        subq.columns = [Function("json_agg", json_obj)]
        subq.from_table = related_table
        subq.where_clause = Eq(r_id, p_id)
        likes_coalesced = Coalesce(subq, Value("[]", inline=True))
        
        # self.curr_query.columns.append(likes_coalesced)
        self._add_columns(Value(rel.name), likes_coalesced)
        self.curr_query = json_obj
        self.curr_model = related_model
        self.curr_table = related_table
        
    def _add_columns(self, *args):
        if self.query_depth == 1:
            self.query.columns.extend(list(args))
        else:
            args = self.args + args            

    # def order_by(self, *fields: str) -> "SelectQuerySet[MODEL]":
    #     self.query.order_by(*[Column(f, self.table) for f in fields])
    #     return self
    def order_by(self, *fields: str) -> "SelectQuerySet[MODEL]":
        orderings = []
        for field in fields:
            direction = "ASC"
            if field.startswith("-"):
                direction = "DESC"
                field = field[1:]
            orderings.append(OrderBy(Column(field, self.curr_table), direction))

        self.query.order_by_(*orderings)
        return self


    def limit(self, n: int) -> "SelectQuerySet[MODEL]":
        self.query.limit_(n)
        return self

    def offset(self, n: int) -> "SelectQuerySet[MODEL]":
        self.query.offset_(n)
        return self
    
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        self.order_by(self.model_class.get_key_field())
        self.limit(1)
        return QuerySetSingleAdapter(self)
    
    def last(self) -> "QuerySetSingleAdapter[MODEL]":
        self.order_by("-" + self.model_class.get_key_field())
        self.limit(1)
        return QuerySetSingleAdapter(self)
    


    def render(self) -> str:
        compiler = Compiler()
        sql, params = compiler.compile(self.query)
        self._params = params
        return sql
    
    
    async def execute(self) -> List[MODEL]:
        sql = self.render()
        if self.namespace.is_versioned:
            results = await self.execute_versioned_sql(
                self.namespace.table_name,
                sql,
                is_event_source=self.namespace.is_artifact,
                # turn_limit= ,
                # turn_direction= ,
            )
        else:
            results = await self.execute_sql(sql, *self._params)
        return [self.model_class(**self.namespace.pack_record(dict(row))) for row in results]



    async def execute_sql(self, sql: str, *params: Any):
        return await PGConnectionManager.fetch(sql, *params)
    
    

    
    async def execute_versioned_sql(
        self, 
        table_name: str,
        sql: str,  
        is_event_source: bool = True, 
        turn_limit: int | None = None, 
        turn_direction: str = "DESC",
        branch_id: int | None = None,
    ) -> List[Any]:
        filtered_alias = f"filtered_{table_name}"
        sql = sql.replace(table_name, filtered_alias)       
        if turn_limit:
            turn_order_by_clause = f"ORDER BY t.index {turn_direction} LIMIT {turn_limit}"
        else:
            turn_order_by_clause = ""

        
        turn_where_clause = []
        # if partition_id is not None:
        #     turn_where_clause.append(f"t.partition_id = {partition_id}")
        if is_event_source:
            turn_where_clause.append("m.deleted_at IS NULL")
        turn_where_clause = " AND ".join(turn_where_clause)
        if turn_where_clause:
            turn_where_clause = f"WHERE {turn_where_clause}"
        
        event_source_select_clause = " DISTINCT ON (m.artifact_id)" if is_event_source else ""
        event_source_order_by_clause = "ORDER BY m.artifact_id, m.version DESC" if is_event_source else ""

        versioned_sql = f"""
            WITH RECURSIVE branch_hierarchy AS (
                SELECT
                    id,
                    name,
                    forked_from_index,
                    forked_from_branch_id,
                    current_index AS start_turn_index
                FROM branches
                WHERE id = {branch_id}
                
                UNION ALL
                
                SELECT
                    b.id,
                    b.name,
                    b.forked_from_index,
                    b.forked_from_branch_id,
                    bh.forked_from_index AS start_turn_index
                FROM branches b
                JOIN branch_hierarchy bh ON b.id = bh.forked_from_branch_id
            ),
            turn_hierarchy AS (
                SELECT t.* 
                FROM branch_hierarchy bh
                JOIN turns t ON bh.id = t.branch_id
                WHERE t.index <= bh.start_turn_index AND t.status != 'reverted'
                {turn_order_by_clause}
            ),
            {filtered_alias} AS (
                SELECT{event_source_select_clause}
                    m.*
                FROM turn_hierarchy t               
                JOIN "{table_name}" m ON t.id = m.turn_id
                {turn_where_clause}
                {event_source_order_by_clause}
            )
            {sql}
            """
        # versioned_sql = textwrap.dedent(versioned_sql)
        results = await PGConnectionManager.fetch(versioned_sql)
        return [dict(row) for row in results]