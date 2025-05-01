import textwrap
from typing import Dict, Generic, List, Literal, Set, Tuple
from typing_extensions import TypeVar

from promptview.model2.postgres.query_parser import build_where_clause
from promptview.model2.query_filters import QueryFilter, QueryProxy


class Renderable:
    
    def render(self, new_line: bool = True):
        raise NotImplementedError("Subclasses must implement this method")

class Query(Renderable):
    
    
    @property
    def outputs(self):
        raise NotImplementedError("Subclasses must implement this method")
    



# class SelectField(Renderable):
    
#     def __init__(
#         self, 
#         field: str | Query,
#         alias: str | None = None,
#     ):    
#         if isinstance(field, str):
#             self.field = field
#             self.alias = alias
#         else:
#             self.field = None
#             self.alias = alias
#             if alias is None:
#                 raise ValueError("Alias is required for subqueries")
#             self.query = field
        
#     @property
#     def name(self):
#         return self.alias or self.field
    
#     def render(self):
#         if self.field:
#             if self.alias:
#                 return f"{self.field} AS {self.alias}"
#             return self.field
#         else:
#             return self.query.render()

SelectType = str | Tuple[str, str] | Tuple[Query, str]
    
class Join:
    
    def __init__(
        self,
        primary_table: str,
        primary_key: str,
        foreign_table: str,
        foreign_key: str,
        alias: str | None = None,
    ):
        self.primary_table = primary_table
        self.primary_key = primary_key
        self.foreign_table = foreign_table
        self.foreign_key = foreign_key
        self.alias = alias
        
    def render(self, new_line: bool = True):
        sql = f'JOIN "{self.foreign_table}" AS {self.alias} ON "{self.primary_table}"."{self.primary_key}" = "{self.foreign_table}"."{self.foreign_key}"'
        if new_line:
            sql += "\n"
        return sql
        

class Coalesce(Query):
    
    def __init__(self, query: Query, default: str):
        self.query = query
        self.default = default
        
    def render(self, new_line: bool = True):
        coalesce_sql = f"COALESCE(\n"
        coalesce_sql += "  (\n"
        coalesce_sql += textwrap.indent(self.query.render(True), "    ")
        coalesce_sql += f'  ), "{self.default}"' + "\n"
        coalesce_sql += f")"
        if new_line:
            coalesce_sql += "\n"
        return coalesce_sql
        
class JsonBuild(Query):
    
    def __init__(
        self,
        table_name: str,
        select: List[SelectType],
    ):
        self.table_name = table_name
        self.select = select
        
    def render_field(self, field: SelectType):
        if isinstance(field, str):
            return f'"{field}": {self.table_name}."{field}"'
        elif isinstance(field, tuple):            
            if isinstance(field[0], str):
                return f'"{field[0]}": {self.table_name}."{field[1]}"'
            else:
                return f'"{field[1]}": '+ field[0].render()
        else:
            return field.render()
                
    def render(self, new_line: bool = True):
        sql = "jsonb_build_object(\n"
        fields_sql = ",\n".join([self.render_field(field) for field in self.select]) + "\n"
        sql += textwrap.indent(fields_sql, "    ")
        sql += ")"        
        if new_line:
            sql += "\n"
        return sql
        

class JsonAgg(Query):
    
    def __init__(
        self,
        query: Query,
        # table_name: str,
        # alias: str | None = None,
        filter: str | None = None,
        distinct: bool = False,
    ):
        self.query = query
        # self.table_name = table_name
        # self.alias = alias
        self.distinct = distinct
        self.filter = filter
        
    def render(self, new_line: bool = True):
        sql = f"json_agg(\n"
        if self.distinct:
            sql += " DISTINCT ON (id)"
        sql += f"  {self.query.render()}"
        if sql.endswith("\n"):
            sql = sql[:-1]
        if self.filter:
            sql += f" FILTER (WHERE {self.filter})"
        sql += ")"
        if new_line:
            sql += "\n"
        return sql


class Where(Query):
    
    def __init__(self, statment: QueryFilter |  Dict[str, str] | str, alias: str | None = None):
        self.statment = statment
        self.alias = alias
        
    def render(self, new_line: bool = True):
        if isinstance(self.statment, QueryFilter):
            sql = f"WHERE {build_where_clause(self.statment, self.alias)}"
        elif isinstance(self.statment, dict):
            raise ValueError("Where clause cannot be a dictionary")
        else:
            sql = f"WHERE {self.statment}"
        if new_line:
            sql += "\n"
        return sql
    
    
    
class SelectQuery(Query):
    
    def __init__(
        self, 
        select: List[str | Tuple[str, str] | Tuple[Query, str]] | Literal["*"] | Query | None,
        from_table: str,
        alias: str | None = None,        
        joins: list[Join] | None = None,
        where: Where | None = None,
    ):
        self._table_name = from_table
        self._alias = alias
        self._select = select
        self._joins = joins or []
        self._where = where
        
        
    @property
    def outputs(self):
        return {field.name: field for field in self._select.values()}
    
    def alias(self, alias: str):
        self._alias = alias
        if self._where:
            self._where.alias = alias
        return self
    
    def where(self, where: QueryFilter |  Dict[str, str] | str):
        self._where = Where(where, self._alias)
        return self
    
    
    def join(self, primary_table: str, primary_key: str, foreign_table: str, foreign_key: str, alias: str | None = None):
        self._joins.append(Join(primary_table, primary_key, foreign_table, foreign_key, alias))
        return self
    
    def render_field(self, field: str | Dict[str, str] | Dict[str, Query]):
        if isinstance(field, str):
            return field
        elif isinstance(field, tuple):
            if isinstance(field[0], str):
                return f"{field[0]} AS {field[1]}"
            else:
                return f"{field[0].render(False)} AS {field[1]}"
        else:
            raise ValueError(f"Invalid field type: {type(field)}")
        
    def render_select(self):
        if isinstance(self._select, list):
            return ",\n".join([self.render_field(field) for field in self._select]) + "\n"
        elif self._select == "*":
            return f'"{self._alias}".*\n' if self._alias else "*\n"
        else:
            return self._select.render()

    def render(self, new_line: bool = True):
        sql = f"SELECT \n"
        # if isinstance(self.select, list):
        #     fields_sql = ",\n".join([self.render_field(field) for field in self.select]) + "\n"
        #     sql += textwrap.indent(fields_sql, "    ")
        # elif self.select == "*":
        #     sql += f'"{self.alias}".*\n' if self.alias else "*\n"
        # else:
        #     raise ValueError(f"Invalid select type: {type(self.select)}")
        sql += textwrap.indent(self.render_select(), "    ")
        sql += f'FROM "{self._table_name}"'
        if self._alias:
            sql += f" AS {self._alias}"
        
        if self._joins:
            sql += "\n"
            for join in self._joins:
                sql += join.render()
        if self._where:
            sql += "\n"
            sql += self._where.render()
        if new_line:
            sql += "\n"
        return sql
    
    
    
    
    
    
    
    



# class PgQuerySet:
    
#     def __init__(self, query: Query):
#         self.query = query
        
#     def render(self, new_line: bool = True):
#         return self.query.render(new_line)
    
    