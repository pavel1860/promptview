from dataclasses import dataclass
from functools import reduce
import json
from operator import and_
from typing import Any, Callable, Generator, Generic, List, Optional, OrderedDict, Self, Type, Union
from typing_extensions import TypeVar
from promptview.model3.base.base_namespace import BaseNamespace, RelationPlan
from promptview.model3.model3 import Model
from promptview.model3.postgres2.rowset import RowsetNode
from promptview.model3.relation_info import RelationInfo
from promptview.model3.sql.joins import Join
from ..sql.queries import CTENode, SelectQuery, Table, Column, NestedSubquery, Subquery
from ..sql.expressions import Coalesce, Eq, Expression, RawSQL, WhereClause, param, OrderBy, Function, Value, Null
from ..sql.compiler import Compiler
from ..sql.json_processor import Preprocessor
from promptview.utils.db_connections import PGConnectionManager

MODEL = TypeVar("MODEL", bound=Model)



class CTERegistry:
    def __init__(self):
        # name -> (query, recursive)
        # self._entries: "OrderedDict[str, tuple[Any, bool]]" = OrderedDict()
        self._entries: "OrderedDict[str, CteSet]" = OrderedDict()
        self.recursive: bool = False

    # def register_raw(self, name: str, query: Union[SelectQuery, RawSQL], *, recursive: bool = False, replace: bool = True):
    #     if replace or name not in self._entries:
    #         if name in self._entries:
    #             del self._entries[name]
    #         self._entries[name] = (query, recursive)
    #     if recursive:
    #         self.recursive = True

    # def register_node(self, node: "CTENode", *, replace: bool = True):
    #     self.register_raw(node.name, node.query, recursive=node.recursive, replace=replace)
    
    def __getitem__(self, name: str):
        return self._entries[name]
    
    def __iter__(self):
        return iter(self._entries.items())
    
    def register(self, cte_qs: "PgSelectQuerySet", name: str | None = None, alias: str | None = None) -> "CteSet":
        if name is None:
            raise ValueError("CTE must have an alias")
        cte_set = CteSet(cte_qs, name=name, alias=alias or cte_qs.alias)
        self._entries[name] = cte_set
        if cte_qs.recursive:
            self.recursive = True
        return cte_set
    
    def register_cte_set(self, cte_set: "CteSet"):
        self._entries[cte_set.name] = cte_set
        if cte_set.recursive:
            self.recursive = True
        return cte_set
    
    def clear(self):
        self._entries.clear()
        self.recursive = False

    def merge(self, other: "CTERegistry"):
        # last-writer-wins; preserve incoming order
        for name, cte_qs in other._entries.items():
            self.register_cte_set(cte_qs)
        if other.recursive:
            self.recursive = True
            

    def import_from_queryset(self, q: "PgSelectQuerySet", *, clear_source: bool = True):
        if q._cte_registry:
            for name, cte_qs in q._cte_registry:
                # compiler expects name->query tuples; no 'recursive' per item in your current shape
                self.register(cte_qs, name)
        q._cte_registry = self

    def to_list(self) -> list[tuple[str, Any]]:
        # drop the recursive flag per-item; Compiler already takes query.recursive
        return [(name, cte_qs) for name, cte_qs in self._entries.items()]





class QueryProxy:
    """
    Proxy for building column expressions from a model.
    Allows lambda m: m.id > 5 style filters.
    """
    def __init__(self, model_class, table):
        self.model_class = model_class
        self.table = table

    def __getattr__(self, field_name):
        return Column(field_name, self.table)


T_co = TypeVar("T_co", covariant=True)

class QuerySetSingleAdapter(Generic[T_co]):
    def __init__(self, queryset: "PgSelectQuerySet[T_co]"):
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



class OrderingSet:
    
    
    def __init__(self, namespace: BaseNamespace, from_table: Table):
        self.namespace = namespace
        self.from_table = from_table
        self.order_by: list[OrderBy] = []
        self.limit: int | None = None
        self.offset: int | None = None
        self.distinct_on: list[Column] | None = None
        self.group_by: list[Column] = []
    
    
    def infer_order_by(self, *fields: str):
        for field in fields:
            direction = "ASC"
            if field.startswith("-"):
                direction = "DESC"
                field = field[1:]
            self.order_by.append(OrderBy(Column(field, self.from_table), direction))
        

    def self_group(self, field: str | None = None):
        if field is None:
            self.group_by += [Column(self.namespace.primary_key, self.from_table)]
        else:
            self.group_by += [Column(field, self.from_table)]
        
        
class SelectionSet:
    def __init__(self, namespace: BaseNamespace, from_table: Table):
        self.namespace = namespace
        self.from_table = from_table
        self.expressions = []
        self.clause = WhereClause()
        
    def select_condition(self, condition: Callable[[MODEL], bool]):        
        if callable(condition):
            proxy = QueryProxy(self.namespace._model_cls, self.from_table)
            expr = condition(proxy)
        else:
            expr = condition  # Already an Expression
        self.expressions.append(expr)
        
    def select(self, **kwargs):
        for field, value in kwargs.items():
            col = Column(field, self.from_table)
            self.expressions.append(Eq(col, param(value)))
            
            
    def relation(self, relation: RelationInfo):
        self.clause &= Eq(Column(relation.primary_key, self.from_table), Column(relation.foreign_key, self.from_table))
        
            
    def reduce(self):
        if self.expressions:
            expr = reduce(and_, self.expressions)
            self.clause &= expr
        return self.clause

class TableRegistry:
    
    def __init__(self):
        self.alias_lookup = {}
        
    def register(self, name: str, alias: str):
        self.alias_lookup[name] = alias
        
    def gen_alias(self, name: str) -> str:
        base = name[0].lower()
        alias = base
        i = 1
        while alias in self.alias_lookup:
            alias = f"{base}{i}"
            i += 1
        return alias
    
    def confirm_alias(self, alias: str):
        i = 1
        while alias in self.alias_lookup:
            alias = f"{alias}{i}"
            i += 1
        return alias
    
    def register_ns(self, namespace: BaseNamespace, table_name: str | None = None, alias: str | None = None):        
        table_name = table_name or namespace.name
        if alias:
            if alias in self.alias_lookup:
                raise ValueError(f"Alias {alias} for namespace {namespace.name} already in use by {self.alias_lookup[alias]}")
            self.alias_lookup[table_name] = alias
            return Table(table_name, alias=self.alias_lookup[table_name])
        # if table_name in self.alias_lookup:
            # return Table(table_name, alias=self.alias_lookup[table_name])
        else:
            alias = self.gen_alias(table_name)
            self.alias_lookup[table_name] = alias
            return Table(table_name, alias=alias)
        
    
    def get_ns_table(self, namespace: BaseNamespace, table_name: str | None = None, alias: str | None = None) -> Table:        
        table_name = table_name or namespace.name
        if table_name in self.alias_lookup:
            return Table(table_name, alias=self.alias_lookup[table_name])
        else:
            alias = self.gen_alias(table_name)
            self.alias_lookup[table_name] = alias
            return Table(table_name, alias=alias)
    
    def merge_registries(self, other: "TableRegistry"):
        for name, alias in other.alias_lookup.items():
            if name not in self.alias_lookup:
                self.alias_lookup[name] = alias
            else:
                self.alias_lookup[name] = self.confirm_alias(alias)



ColumnParamType = str | Column | tuple[str, str]

class ProjectionSet:
    def __init__(self, namespace: BaseNamespace, from_table: Table):
        self.namespace = namespace
        self.from_table = from_table
        self.columns = []
        self.nest_columns: list[tuple["PgSelectQuerySet", str]] = []
        self.used_columns_set = set()
        
    @property
    def is_empty(self):
        return not self.columns and not self.nest_columns
        
    def nest(self, target: "PgSelectQuerySet", name: str | None = None) -> "PgSelectQuerySet":
        self.nest_columns.append((target, name))
        return target
    
    def append(self, col: ColumnParamType) -> Column | None:
        if isinstance(col, str):
            col = Column(col, self.from_table)
        elif isinstance(col, tuple):
            col = Column(col[0], self.from_table, alias=col[1])
        elif isinstance(col, Column):
            col = col
        else:
            raise ValueError(f"Invalid column type: {type(col)}")
        if col.name in self.used_columns_set:
            return
        self.columns.append(col)
        self.used_columns_set.add(col.name)
        return col
    
    def iter_fields(self):
        for col in self.columns:
            field = self.namespace.get_field(col.name)
            yield col.alias_or_name, field
            
    def iter_relations(self):
        for qs, name in self.nest_columns:
            relation = qs.namespace.get_relation(name)
            yield name, relation
    
    def __getitem__(self, name: str):
        for col in self.columns:
            if col.name == name or col.alias == name:
                return col
        raise KeyError(f"Field {name} not found")
    
        
    def __call__(self, *fields: ColumnParamType):
        if len(fields) == 1 and fields[0] == "*":
            for f in self.namespace.iter_fields():
                self.append(f.name)
        else:
            for f in fields:
                self.append(f)
        return self
    
    def copy(self, projection_set: "ProjectionSet", from_table: Table):
        for col in projection_set.columns:
            self.append(Column(name=col.name, table=from_table, alias=col.alias))
        # for qs, name in projection_set.nest_columns:
        #     self.nest(qs, name) #TODO understand if this is needed
        return self
            
            
    def resulve_columns(self):        
        columns = []       
        for qs, name in self.nest_columns:
            nested_query =qs.to_json_query()
            columns.append(Column(
                name=name,
                table=nested_query,
            ))
        return self.columns + columns



class JoinSet:
    
    def __init__(self):        
        self._joins = []
        
    @property
    def joins(self):
        return [join for join, _ in self._joins if join is not None]
    
    @property
    def relations(self):
        return [relation for _, relation in self._joins]
        
    def append(self, relation: RelationInfo, join: Join | None = None):
        self._joins.append((join, relation))
    
    def __getitem__(self, idx: int):
        return self._joins[idx]
    
    def get_join(self, idx: int):
        return self._joins[idx][0]
    
    def get_relation(self, idx: int):
        return self._joins[idx][1]
    
    def __len__(self):
        return len(self._joins)
    
    def __iter__(self):
        return iter(self._joins)


class QuerySet(Generic[MODEL]):
    
    def __init__(
        self, 
        model_class: Type[MODEL], 
        table_registry: TableRegistry | None = None, 
        table_name: str | None = None,
        alias: str | None = None
    ):
        self.model_class = model_class
        self.namespace = model_class.get_namespace()
        self.table_registry = table_registry or TableRegistry()
        # self.table = self.table_registry.get_ns_table(self.namespace, table_name)
        self.table = self.table_registry.register_ns(self.namespace, table_name, alias=alias)
        self.projection_set = ProjectionSet(self.namespace, self.table)        
    
    def build_query(self):
        raise NotImplementedError("Subclasses must implement build_query")
    
    @property
    def alias(self):
        return self.table.alias
    
    def get_field(self, name):
        return self.projection_set[name]   
        
class CteSet(QuerySet[MODEL]):
    
    def __init__(
        self, 
        query_set: "PgSelectQuerySet[MODEL]", 
        name: str, 
        alias: str | None = None,
        recursive: bool | None = None,        
    ):
        super().__init__(query_set.model_class, query_set.table_registry, table_name=name, alias=alias)
        self.projection_set.copy(query_set.projection_set, self.table)
        self.query_set = query_set
        self.name = name
        self.recursive = recursive if recursive is not None else query_set.recursive
       
    
    def build_query(self):
        return self.query_set.build_query()
       

class PgSelectQuerySet(QuerySet[MODEL]):
    def __init__(
        self, 
        model_class: Type[MODEL], 
        alias: str | None = None, 
        cte_registry: CTERegistry | None = None,
        table_registry: TableRegistry | None = None,
        recursive: bool = False
    ):
        super().__init__(model_class, table_registry, alias=alias)
        # self.model_class = model_class
        # self.namespace = model_class.get_namespace()
        # self.table_registry = table_registry or TableRegistry()
        # table = Table(self.namespace.name, alias=alias or self._gen_alias(self.namespace.name))
        # self.table = self.table_registry.get_ns_table(self.namespace)
        # self.projection_set = ProjectionSet(self.namespace, self.table)
        self.selection_set = SelectionSet(self.namespace, self.table)
        
        self.ordering_set = OrderingSet(self.namespace, self.table)
        # self.alias = alias
        self._raw_sql = None
        # self.query = query or SelectQuery().from_(self.table)
        self.recursive = recursive
        self._cte_registry = cte_registry or CTERegistry()
        self._rowsets: "OrderedDict[str, RowsetNode]" = OrderedDict()
        self.join_set = JoinSet()


    
    def __await__(self):
        return self.execute().__await__()

    
    def raw_sql(self, sql: str, columns: list[ColumnParamType] | None = None):
        if columns:
            self.projection_set(*columns)
        self._raw_sql = RawSQL(sql)
        return self
            
        
    def use_cte(self, cte, name: str | None = None, alias: str | None = None, on: tuple[str, str] | None = None):
        query_set = self._resolve_query_set_target(cte)
        cte_set = self._cte_registry.register(query_set, name, alias=alias)        
        self.join(cte_set, on=on)
        return self


    def select(self, *fields: str):
        self.projection_set(*fields)
        return self


    def where(
        self,
        condition: Callable[[MODEL], bool] | None = None,
        # condition: Callable[[QueryProxy], Expression] | Expression | None = None,
        **kwargs: Any
    ) -> Self:
        """
        Add a WHERE clause to the query.
        condition: callable taking a QueryProxy or direct Expression
        kwargs: field=value pairs, ANDed together
        """
        # Callable condition: lambda m: m.id > 5
        if condition is not None:
            self.selection_set.select_condition(condition)
        # kwargs: field=value
        if kwargs:
            self.selection_set.select(**kwargs)
        return self

    def filter(self, condition=None, **kwargs):
        """Alias for .where()"""
        return self.where(condition, **kwargs)
    
    def join(self, target: "Type[Model] | QuerySet", on: tuple[str, str] | None = None, nest_as: str | None = None):
        query_set = self._resolve_query_set_target(target)
        relation = self._get_qs_relation(query_set, on=on)
        
        # relation = self.namespace.get_relation_by_type(target)        
        if relation.is_many_to_many:
            junction_ns = relation.relation_model.get_namespace()
            jt = self.table_registry.get_ns_table(junction_ns)
            
            join = Join(jt, Eq(Column(relation.primary_key, self.table), Column(relation.junction_keys[0], jt)))
            self.join_set.append(relation, join)
            j_join = Join(jt, Eq(Column(relation.foreign_key, query_set.table), Column(relation.junction_keys[1], jt)))            
            self.join_set.append(relation, j_join)
            
            # self.selection_set.clause &= Eq(Column(relation.primary_key, self.table), Column(relation.junction_keys[0], jt))
        else:
            # self.selection_set.clause &= Eq(Column(relation.foreign_key, query_set.table), Column(relation.primary_key, self.table))
            join = Join(query_set.table, Eq(Column(relation.foreign_key, query_set.table), Column(relation.primary_key, self.table)))
            self.join_set.append(relation, join)
        if nest_as:
            self.projection_set.nest(query_set, nest_as)
        return self
            
            
    def agg(self, name: str, target: "Type[Model] | QuerySet", on: tuple[str, str] | None = None):
        query_set = self._resolve_query_set_target(target)
        relation = self._get_qs_relation(query_set, on=on)
        query_set.selection_set.clause &= Eq(Column(relation.foreign_key, query_set.table), Column(relation.primary_key, self.table))
        self.projection_set.nest(query_set, name)
        return self
        


    
    def _get_qs_relation(self, query_set: "PgSelectQuerySet", on: tuple[str, str] | None = None) -> RelationInfo:        
        rel = self.namespace.get_relation_by_type(query_set.model_class)
        if rel is None:
            if on:
                if not query_set.namespace.has_field(on[1]):
                    raise ValueError(f"Field {on[1]} not found in {query_set.model_class.__name__}")
                if not self.namespace.has_field(on[0]):
                    raise ValueError(f"Field {on[0]} not found in {self.model_class.__name__}")
                rel = self.namespace.build_temp_relation(f"{self.namespace.name}_{query_set.namespace.name}", query_set.namespace, on)
            else:            
                raise ValueError(f"No relation to {query_set.model_class.__name__}")
        return rel
    
    
    def _resolve_query_set_target(self, target: "Type[Model] | QuerySet"):
        if isinstance(target, PgSelectQuerySet):
            self.table_registry.merge_registries(target.table_registry)
            target.table_registry = self.table_registry
            self._cte_registry.merge(target._cte_registry)
            target._cte_registry.clear()
            # target._cte_registry = self._cte_registry
            return target
        elif isinstance(target, CteSet):
            self.table_registry.merge_registries(target.table_registry)
            # target._cte_registry.clear()
            # target.table_registry = self.table_registry
            return target
        elif isinstance(target, type) and issubclass(target, Model):
            return PgSelectQuerySet(target, table_registry=self.table_registry, cte_registry=self._cte_registry)
        else:
            raise ValueError(f"Invalid target: {target}")

    
    def include(self, target: "Type[Model] | PgSelectQuerySet"):        
        query_set = self._resolve_query_set_target(target)
        relation = self._get_qs_relation(query_set)
        # query_set.alias = relation.name
        query_set.select("*")
        if relation.is_many_to_many:
            if relation.relation_model is None:
                raise ValueError(f"No relation model for {relation.name}")
            jt = self.table_registry.get_ns_table(relation.relation_namespace)
            join = Join(jt, Eq(Column(relation.junction_keys[1], jt), Column(relation.foreign_key, query_set.table)))
            query_set.join_set.append(relation, join)
            query_set.selection_set.clause &= Eq(Column(relation.primary_key, self.table), Column(relation.junction_keys[0], jt))
        else:
            query_set.selection_set.clause &= Eq(Column(relation.foreign_key, query_set.table), Column(relation.primary_key, self.table))
            query_set.join_set.append(relation)
        
        self.projection_set.nest(query_set, relation.name)
        return self
            
        
      

    def order_by(self, *fields: str) -> "PgSelectQuerySet[MODEL]":
        self.ordering_set.infer_order_by(*fields)
        return self
    
    def limit(self, n: int) -> "PgSelectQuerySet[MODEL]":
        self.ordering_set.limit = n
        return self
    
    def offset(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """Skip the first `n` rows."""
        self.ordering_set.offset = n
        return self
    
    def distinct_on(self, *fields: str) -> "PgSelectQuerySet[MODEL]":
        """
        Postgres-specific DISTINCT ON.
        Keeps only the first row of each set of rows where the given columns are equal.
        """
        self.ordering_set.distinct_on = [Column(f, self.from_table) for f in fields]
        return self
    
    def first(self) -> "QuerySetSingleAdapter[MODEL]":
        """Return only the first record."""
        self.order_by(self.namespace.default_order_field)
        self.limit(1)
        return QuerySetSingleAdapter(self)

    def last(self) -> "QuerySetSingleAdapter[MODEL]":
        """Return only the last record."""
        self.order_by("-" + self.namespace.default_order_field)
        self.limit(1)
        return QuerySetSingleAdapter(self)

    def head(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """
        Return the first `n` rows ordered by the model's default temporal field.
        """
        self.order_by(self.namespace.default_order_field)
        self.limit(n)
        return self

    def tail(self, n: int) -> "PgSelectQuerySet[MODEL]":
        """
        Return the last `n` rows ordered by the model's default temporal field.
        """
        self.order_by("-" + self.namespace.default_order_field)
        self.limit(n)
        return self
    
    
    
    def print(self):
        sql, params = self.render()
        print("----- QUERY -----")
        print(sql)
        print("----- PARAMS -----")
        print(params)
        return self
    
    
    def build_query(
        self, 
        include_columns: bool = True,
        self_group: bool = True,
        include_ctes: bool = True
    ):
        if self._raw_sql:
            return self._raw_sql
        if self.projection_set.is_empty:
            raise ValueError(f"No columns selected for query {self.model_class.__name__}. Use .select() to select columns.")
        query = SelectQuery().from_(self.table)
        query.where = self.selection_set.reduce()
        if self.projection_set.nest_columns and self_group:
            self.ordering_set.self_group()
        query.group_by = self.ordering_set.group_by
        query.order_by = self.ordering_set.order_by
        query.limit = self.ordering_set.limit
        query.offset = self.ordering_set.offset
        query.joins = self.join_set.joins
        if include_columns:
            query.columns = self.projection_set.resulve_columns()
        if include_ctes:
            for name, cte_qs in self._cte_registry:
                query.with_cte(name, cte_qs.build_query(), recursive=self._cte_registry.recursive)
        return query
    
    
    
    def to_json_query(self):
        print("jsonify", self.alias)
        query = self.build_query(
            include_columns=False, 
            self_group=False, 
            include_ctes=False
        )
        json_pairs = []
        for col in self.projection_set.columns:
            json_pairs.append(Value(col.alias or col.name))
            json_pairs.append(col)
        
        for qs, name in self.projection_set.nest_columns:
            nested_query = qs.to_json_query()
            # json_pairs.append(Value(qs.alias))
            json_pairs.append(Value(name))
            json_pairs.append(nested_query)
            
        json_obj = Function("jsonb_build_object", *json_pairs)
        
        if len(self.join_set):
            join, relation = self.join_set[0]
            if relation is not None and not relation.is_one_to_one:
                json_obj = Function("json_agg", json_obj)
                default_value = Value("[]", inline=True)
            else:
                default_value = Null()
                
            query.select(json_obj)
            return Coalesce(query, default_value)
        else:
            json_obj = Function("json_agg", json_obj)
            query.select(json_obj)
            default_value = Value("[]", inline=True)
            return Coalesce(query, default_value)
            return json_obj
        # else:
        #     json_obj = Function("json_agg", json_obj)
        #     return json_obj
            raise ValueError("No joins found")
    
    
    def parse_row(self, row: dict[str, Any]) -> MODEL:
        # Convert scalar columns first
        data = dict(row)        
        data = self.namespace.deserialize(data)

        return self.model_class(**data)
  
    
    def parse_json_row(self, row: dict[str, Any]) -> MODEL:
        data = dict(row)
        data = self.namespace.deserialize(data, with_rels=False)
        for nest_qs, nest_col in self.projection_set.nest_columns:
            value = data.get(nest_col, None)
            if value is None:
                raise ValueError(f"No value for {nest_col} but it was requested")
            if isinstance(value, str):
                value = json.loads(value)
            data[nest_col] = value
        return data


    def deserialize_row(self, row):
        data = dict(row)
        for name, field in self.projection_set.iter_fields():
            value = data.get(name, None)
            if value is None and not field.is_optional:
                raise ValueError(f"No value for field '{name}' but it was requested")
            data[name] = field.deserialize(value)
        for nest_qs, name in self.projection_set.nest_columns:
            value = data.get(name, None)
            if value is None:
                raise ValueError(f"No value for field '{name}' but it was requested")
            if isinstance(value, str):
                value = json.loads(value)
            data[name] = value
        return data
            
    
    def render(self) -> tuple[str, list[Any]]:
        query = self.build_query()        
        compiler = Compiler()
        # processor = Preprocessor()
        # compiled = processor.process_query(query)
        sql, params = compiler.compile(query)
        return sql, params
    
    async def json(self):
        return await self.execute_json()
    
    async def execute_json(self):   
        sql, params = self.render()
        rows = await PGConnectionManager.fetch(sql, *params)
        return [self.deserialize_row(row) for row in rows]

    async def execute(self) -> List[MODEL]:
        sql, params = self.render()
        rows = await PGConnectionManager.fetch(sql, *params)
        return [self.parse_row(dict(row)) for row in rows]







def select(model_class: Type[MODEL]) -> "PgSelectQuerySet[MODEL]":
    return model_class.query().select("*")
    # return PgSelectQuerySet(model_class).select("*")