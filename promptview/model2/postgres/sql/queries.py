




import re
from typing import Literal
from promptview.model2.postgres.sql.joins import Join
from promptview.model2.postgres.sql.expressions import Eq, Expression, Neq, Gt, Gte, Lt, Lte, OrderBy, Value, param

class Table:
    def __init__(self, name, alias=None):
        self.name = name
        self.alias = alias
        
        
    def __str__(self):
        return self.alias or self.name

    def __repr__(self):
        return f"<Table {self.name} AS {self.alias}>" if self.alias else f"<Table {self.name}>"


def is_camel_case(name: str) -> bool:
    return bool(re.fullmatch(r'[a-z]+(?:[A-Z][a-z]*)+', name))


class Column:
    def __init__(self, name, table=None, alias=None):
        # some table coumns have camel case names
        #the query returned parenthesized column name if it is camel case
        # self.name = name
        self.name = name if not is_camel_case(name) else f'"{name}"'
        # self.name = name if all(c.islower() for c in name) else f'"{name}"'
        self.table = table
        self.alias = alias
        
    def __str__(self):
        prefix = f"{str(self.table)}." if self.table else ""
        base = f"{prefix}{self.name}"
        return f"{base} AS {self.alias}" if self.alias else base

    def __repr__(self):
        return str(self)
    
    
    # Inside Column class (or better: a ColumnExpression wrapper if you want to separate it from raw SQL)

    def __eq__(self, other):
        return Eq(self, param(other) if not isinstance(other, Expression) else other)

    def __ne__(self, other):
        return Neq(self, param(other) if not isinstance(other, Expression) else other)

    def __gt__(self, other):
        return Gt(self, param(other) if not isinstance(other, Expression) else other)

    def __ge__(self, other):
        return Gte(self, param(other) if not isinstance(other, Expression) else other)

    def __lt__(self, other):
        return Lt(self, param(other) if not isinstance(other, Expression) else other)

    def __le__(self, other):
        return Lte(self, param(other) if not isinstance(other, Expression) else other)


JoinType = Literal["LEFT", "RIGHT", "INNER"]

class SelectQuery:
    def __init__(self):
        self.columns = []
        self.from_table = None
        self.joins = []
        self.where_clause = None
        self.group_by = []
        self.having = None
        self.order_by = []
        self.limit = None
        self.offset = None
        self.distinct = False
        self.distinct_on = [] 
        self.alias = None
        self.ctes = []  
        self.recursive = False  # <-
    
    
    def join(self, table, condition, join_type='LEFT', alias=None):
        self.joins.append(Join(table, condition, join_type, alias))
        return self

    def left_join(self, table, condition, alias=None):
        return self.join(table, condition, 'LEFT', alias)

    def right_join(self, table, condition, alias=None):
        return self.join(table, condition, 'RIGHT', alias)

    def inner_join(self, table, condition, alias=None):
        return self.join(table, condition, 'INNER', alias)
    
    
    def select(self, *columns):
        self.columns = list(columns)
        return self

    def from_(self, table):
        self.from_table = table
        return self

    def where(self, condition):
        self.where_clause = condition
        return self

    def group_by_(self, *cols):
        self.group_by = list(cols)
        return self

    def order_by_(self, *cols):
        self.order_by = list(cols)
        return self

    def limit_(self, count):
        self.limit = count
        return self

    def offset_(self, count):
        self.offset = count
        return self

    def with_cte(self, name, query, recursive: bool = False):
        self.ctes.append((name, query))
        if self.recursive == False:
            self.recursive = recursive
        return self

    def distinct_(self, enabled=True):
        self.distinct = enabled
        return self
        
    def distinct_on_(self, *cols):
        self.distinct_on = list(cols)
        return self


class Subquery:
    def __init__(self, query: SelectQuery, alias: str):
        self.query = query
        self.alias = alias      
        
        
class InsertQuery:
    def __init__(self, table):
        self.table = table
        self.columns = []
        self.values = []  # List of rows (each row is a list of values)
        self.returning = []
        self.on_conflict = None  # Optional: for UPSERT



class UpdateQuery:
    def __init__(self, table):
        self.table = table
        self.set_clauses = []
        self.where_clause = None
        self.returning = []
        
    def set(self, values: list[tuple[Column, Value]]):
        self.set_clauses = values
        return self


class DeleteQuery:
    def __init__(self, table):
        self.table = table
        self.where_clause = None
        self.returning = []





class UnionQuery:
    def __init__(self, left: SelectQuery, right: SelectQuery):
        self.left = left
        self.right = right
        
    
        