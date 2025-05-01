









from typing import Callable, Generic, Type
from typing_extensions import TypeVar

from promptview.model2.base_namespace import Namespace
from promptview.model2.model import Model
from promptview.model2.postgres.fields_query import PgFieldInfo
from promptview.model2.postgres.query_builders2 import Coalesce, Filter, JsonAgg, JsonBuild, SelectQuery, TableName, Where
from promptview.model2.query_filters import QueryProxy


MODEL = TypeVar("MODEL", bound="Model")



    
    
class SelectQuerySet(Generic[MODEL]):
    query: SelectQuery
    
    def __init__(self, model_class: Type[MODEL]):
        self.model_class = model_class
        self.query = SelectQuery(
            select="*",
            from_table=TableName(self.model_class.get_namespace().table_name)
        )

        
    def select(self, *args: str, **kwargs: str) -> "SelectQuerySet[MODEL]":
        fields = list(args) 
        if kwargs:
            fields += [(v, k) for k, v in kwargs.items()]
        self.query._select = fields
        return self
    
    def alias(self, alias: str) -> "SelectQuerySet[MODEL]":
        self.query.alias(alias)
        return self
    
    
    
    def join(self, model: Type[Model] | "SelectQuerySet[Model]") -> "SelectQuerySet[MODEL]":
        if issubclass(model, Model):
            relation = self.namespace.get_relation_by_type(model)
            fields = [f.name for f in model.iter_fields()]
            foreign_table = TableName(model.get_namespace().table_name)
            sub_query = Coalesce(
                JsonAgg(
                    JsonBuild(
                        # table_name="u",
                        table_name=self.query.table_name,
                        select=fields,
                    ),
                    filter=Filter(
                        table_name=foreign_table, 
                        filters={
                            f"{relation.foreign_key}": "IS NOT NULL"
                        }), 
                    
                ),
                default="[]",
            )
            self.query._select += [(sub_query, relation.name)]
            self.query.join(self.query.table_name, relation.primary_key, foreign_table, relation.foreign_key)
        return self
    
    def render(self) -> str:
        return self.query.render()
        
    @property
    def namespace(self) -> Namespace[MODEL, PgFieldInfo]:
        return self.model_class.get_namespace()

    def where(self, filter_fn: Callable[[MODEL], bool] | None = None, **kwargs) -> "SelectQuerySet[MODEL]":
        """Filter the query"""           
        if filter_fn is not None:
            proxy = QueryProxy[MODEL, PgFieldInfo](self.model_class, self.namespace)
            self.query.where(filter_fn(proxy))
        return self
    
    