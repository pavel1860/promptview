









from typing import Any, Callable, Generic, List, Self, Type
from typing_extensions import TypeVar

from promptview.model2.base_namespace import Namespace
from promptview.model2.model import Model
from promptview.model2.postgres.fields_query import PgFieldInfo
from promptview.model2.postgres.query_builders2 import Coalesce, Filter, JsonAgg, JsonBuild, JsonNestedQuery, JsonSubNestedQuery, SelectQuery, TableName, Where
from promptview.model2.query_filters import QueryProxy
from promptview.utils.db_connections import PGConnectionManager


MODEL = TypeVar("MODEL", bound="Model")

ORIG_MODEL = TypeVar("ORIG_MODEL", bound="Model")

QUERY_TYPE = TypeVar("QUERY_TYPE", bound=SelectQuery)

class BaseQuerySet(Generic[MODEL, ORIG_MODEL, QUERY_TYPE]):
    query: QUERY_TYPE
    orig_model: ORIG_MODEL
    
    def __init__(
        self, 
        model_class: Type[MODEL], 
        query: QUERY_TYPE, 
        orig_model: ORIG_MODEL,
        parent_query: "BaseQuerySet | None" = None,
    ):
        self.model_class = model_class
        self.orig_model = orig_model
        self.query = query
        self.orig_query_set = parent_query
        
    @property
    def namespace(self) -> Namespace[MODEL, PgFieldInfo]:
        return self.model_class.get_namespace()
        
        
    # def init_query(self, model_class: Type[MODEL]) -> QUERY_TYPE:
    #     raise NotImplementedError("Subclasses must implement this method")
        
    # def select(self, *args: str, **kwargs: str) -> "SelectQuerySet[MODEL]":
    #     raise NotImplementedError("Subclasses must implement this method")
    
    # def alias(self, alias: str) -> "SelectQuerySet[MODEL]":
    #     raise NotImplementedError("Subclasses must implement this method")
    
    def render(self, new_line: bool = True) -> str:
        return self.query.render(new_line)
        
    def render_orig(self) -> str:
        if self.orig_query_set is None:
            raise ValueError("Parent query is not set")
        return self.orig_query_set.render()  
    
    async def execute_sql(self, sql: str, *values: Any) -> List[Any]:
        return await PGConnectionManager.fetch(sql, *values)
    
    def pack_record(self, data: Any) -> Any:
        """Pack the record for the model"""
        return self.orig_model.get_namespace().pack_record(data)

    
    async def execute(self) -> List[ORIG_MODEL]:
        sql = self.render_orig()
        results = await self.execute_sql(sql)
        return [self.orig_model(**self.pack_record(dict(result))) for result in results] 
    
    
    
class SelectQuerySet(BaseQuerySet[MODEL, MODEL, SelectQuery]):
    query: SelectQuery
    parent_query: SelectQuery | None = None
    main_query: SelectQuery | None = None
    
    
    def __init__(self, model_class: Type[MODEL]):
        # self.model_class = model_class
        query = SelectQuery(
            select="*",
            from_table=TableName(model_class.get_namespace().table_name)
        )
        super().__init__(model_class, query, model_class, self)
        
    def select(self, *args: str, **kwargs: str) -> "SelectQuerySet[MODEL]":
        if len(args) and args[0] == "*":
            fields = [f.name for f in self.model_class.iter_fields()]
        else:    
            fields = list(args) 
            if kwargs:
                fields += [(v, k) for k, v in kwargs.items()]
        self.query._select = fields
        return self
    
    def alias(self, alias: str) -> "SelectQuerySet[MODEL]":
        self.query.alias(alias)
        return self
    
    def join(self, model: Type[Model]) -> "NestedQuerySet[MODEL, Self, JsonNestedQuery]":        
        relation = self.namespace.get_relation_by_type(model)
        fields = [f.name for f in model.iter_fields()]
        foreign_table = TableName(model.get_namespace().table_name)
        query = JsonNestedQuery(
            select=fields,
            from_table=foreign_table,
            parent_table=self.query.table_name,
            primary_key=relation.primary_key,
        )
        nested_query = NestedQuerySet(model, query, self.orig_model, self.orig_query_set)
        self.query.add_select((nested_query, relation.name))
        self.query.join(self.query.table_name, relation.primary_key, foreign_table, relation.foreign_key)
        self.query.group_by(relation.primary_key)
        return nested_query
    

    def where(self, filter_fn: Callable[[MODEL], bool] | None = None, **kwargs) -> "SelectQuerySet[MODEL]":
        """Filter the query"""           
        if filter_fn is not None:
            proxy = QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
            self.query.where(filter_fn(proxy))
        return self
    
    def render(self, new_line: bool = True) -> str:
        return self.query.render(new_line)
    
    
    
    

    
    
class NestedQuerySet(BaseQuerySet[MODEL, ORIG_MODEL,  QUERY_TYPE]):
        
    def __init__(self, model_class: Type[MODEL], query: QUERY_TYPE, orig_model: ORIG_MODEL, parent_query: "BaseQuerySet | None" = None):
        super().__init__(model_class, query, orig_model, parent_query)
    
    
    def select(self, *args: str, **kwargs: str) -> "SelectQuerySet[MODEL]":
        fields = list(args) 
        if kwargs:
            fields += [(v, k) for k, v in kwargs.items()]
        self.query._select = fields
        return self  
    
    def join(self, model: Type[Model]) -> "NestedQuerySet[MODEL, Self, QUERY_TYPE]":
        relation = self.namespace.get_relation_by_type(model)
        fields = [f.name for f in model.iter_fields()]
        foreign_table = TableName(model.get_namespace().table_name)
        query = JsonSubNestedQuery(
            select=fields,
            from_table=foreign_table,
            parent_table=self.query.table_name,
            foreign_key=relation.foreign_key,
        )
        nested_query = NestedQuerySet(model, query, self.orig_model, self.orig_query_set)
        self.query.add_select((nested_query, relation.name))
        self.orig_query_set.query.join(self.query.table_name, relation.primary_key, foreign_table, relation.foreign_key)
        return nested_query


    def alias(self, alias: str) -> "NestedQuerySet[MODEL, ORIG_MODEL, QUERY_TYPE]":
        self.query.alias(alias)
        return self

    
    def where(self, filter_fn: Callable[[MODEL], bool] | None = None, **kwargs) -> "NestedQuerySet[MODEL, ORIG_MODEL, QUERY_TYPE]":
        """Filter the query"""           
        if filter_fn is not None:
            proxy = QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
            self.query.where(filter_fn(proxy))
        return self