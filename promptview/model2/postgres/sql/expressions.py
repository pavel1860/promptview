
from typing import TYPE_CHECKING

from promptview.model2.base_namespace import NSRelationInfo
from promptview.model2.postgres.sql.queries import Column, SelectQuery, Subquery, Table
if TYPE_CHECKING:
    from promptview.model2.postgres.query_set3 import SelectQuerySet





class Expression:
    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __invert__(self):
        return Not(self)




class Value(Expression):
    def __init__(self, value, inline=True):
        self.value = value
        self.inline = inline
        
        
def param(value):
    return Value(value, inline=False)

class Function(Expression):
    def __init__(self, name, *args, alias=None, filter_where=None, distinct=False):
        self.name = name
        self.args = args
        self.alias = alias
        self.filter_where = filter_where
        self.distinct = distinct

    def __str__(self):
        inner = ", ".join(str(arg) for arg in self.args)
        return f"{self.name}({inner})" + (f" AS {self.alias}" if self.alias else "")



class Coalesce(Expression):
    def __init__(self, *values, alias=None):
        self.values = values
        self.alias = alias

def json_build_object(**kwargs):
    args = []
    for key, value in kwargs.items():
        args.append(Value(key))
        args.append(value)
    return Function("jsonb_build_object", *args)




class BinaryExpression(Expression):
    def __init__(self, left, operator: str, right):
        self.left = left
        self.operator = operator
        self.right = right

class Eq(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '=', right)

class Neq(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '!=', right)

class Gt(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '>', right)

class Gte(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '>=', right)

class Lt(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '<', right)

class Lte(BinaryExpression):
    def __init__(self, left, right):
        super().__init__(left, '<=', right)




class And(Expression):
    def __init__(self, *conditions):
        self.conditions = conditions

class Or(Expression):
    def __init__(self, *conditions):
        self.conditions = conditions

class Not(Expression):
    def __init__(self, condition):
        self.condition = condition






class IsNull(Expression):
    def __init__(self, value):
        self.value = value

class In(Expression):
    def __init__(self, value, options):
        self.value = value
        self.options = options  # Can be a list or subquery

class Between(Expression):
    def __init__(self, value, lower, upper):
        self.value = value
        self.lower = lower
        self.upper = upper

class Like(Expression):
    def __init__(self, value, pattern):
        self.value = value
        self.pattern = pattern








class NestedQuery:
    
    
    def __init__(
        self, 
        query: "SelectQuerySet", 
        alias: str, 
        pk_col: Column, 
        parent_query: "SelectQuerySet",
        parent_table: Table,
        rel: NSRelationInfo
    ):
        self.query_set = query
        self.alias = alias
        self.pk_col = pk_col
        self.parent_query = parent_query
        self.parent_table = parent_table
        self.depth = 1
        self.rel = rel
        
    @property
    def name(self):
        return self.alias
        
    @property
    def query(self):
        return self.query_set.query
    
    def update_depth(self):
        for c in self.query.columns:
            if isinstance(c, NestedQuery):
                c.depth = self.depth + 1
                c.update_depth()
    
    # @property
    # def depth(self):
    #     depth = 1
    #     parent = self.parent_query
    #     for i in range(10):
            
    #     return self.parent_query.query_depth + 1
    def build_query(self):
        if self.depth == 1:
            return self.wrap_query_in_json_agg()
        else:
            return self.embed_query_as_subquery()
    
    def wrap_query_in_json_agg(self) -> Coalesce:
        obj = json_build_object(**{col.name: col for col in self.query.columns})
        agg = Function(
            "json_agg",
            obj,
            distinct=True,
            filter_where=Not(IsNull(self.pk_col))
        )
        return Coalesce(agg, Value("[]", inline=True), alias=self.alias)

    def embed_query_as_subquery(self):
        obj = json_build_object(**{
            c.name: c for c in self.query.columns
        })
        subq = SelectQuery()
        subq.columns = [Function("json_agg", obj)]
        subq.from_table = self.query.from_table
        # subq.where_clause = self.query.where_clause
        subq.where_clause = Eq(Column(self.rel.foreign_key, self.query.from_table), Column(self.rel.primary_key, self.parent_table))
        coalesced = Coalesce(subq, Value("[]", inline=True))
        return coalesced
        

    def get_query(self):
        if self.query_set.query_depth == 1:
            return self.wrap_query_in_json_agg()
        else:
            return self.query
