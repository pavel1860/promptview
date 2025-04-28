
import textwrap
from typing import Any, List, Optional, Self, Set
from promptview.model2.postgres.fields_query import NamespaceQueryFields




def build_update_sql(fields: NamespaceQueryFields) -> str:
    sql = (
        f"UPDATE {fields.table_name}\n"
        f"SET\n{textwrap.indent(fields.render_insert(), '    ')}\n"
        f"WHERE {fields.primary_key} = $1\n"
        f"RETURNING {fields.render_return()}\n"
    )
    return sql


def build_insert_sql(fields: NamespaceQueryFields) -> str:
    sql = (
        f"INSERT INTO {fields.table_name} ({fields.render_insert()})\n"
        f"VALUES ({fields.render_placeholders()})\n"
        f"RETURNING {fields.render_return()}\n"
    )
    return sql



# def build_with_clause(queries: list[str]) -> str:
#     return "WITH " + ", ".join(queries) + " AS "




class SqlQuery:
    
    def __init__(
        self, 
        input_fields: NamespaceQueryFields, 
        alias: str | None = None,
        select: Optional[Set[str]] = None,
        labels: Optional[List[dict[str, str]]] = None
    ):
        self.fields = input_fields
        self.alias = alias
        self._select = select
        self._labels = labels or {}
        self._start_idx = 1
        
    def override(self, key: str, value: Any):
        self.fields.override(key, value)
    
    @property
    def inputs(self) -> list[Any]:
        return self.fields.get_inputs()
    
    @property
    def table_name(self) -> str:
        return self.fields.table_name
    
    @property
    def primary_key(self) -> str:
        return self.fields.primary_key
    
    @property
    def outputs(self) -> list[Any]:
        return self.fields.get_outputs()
    
    def render(self) -> str:
        raise NotImplementedError("Subclasses must implement this method")
    
    def indent(self, text: str) -> str:
        return textwrap.indent(text, "    ")
    
    def render_fields(self, select: Set[str] | None = None, alias: str | None = None, labels: dict[str, str] = {}, new_line: bool = True) -> str:
        return self.fields.render(
            select=select or self._select, 
            alias=alias or self.alias, 
            labels=labels or self._labels, 
            new_line=new_line
        )


class SqlContainer:
    
    def __init__(self, queries: list[SqlQuery]):
        self.queries = queries
        prev_len = 1
        for q in self.queries:
            q._start_idx = prev_len
            prev_len += q.fields.inputs_len()
            
    @property
    def outputs(self) -> list[Any]:
        return self.queries[-1].outputs
    
    def render(self) -> str:
        raise NotImplementedError("Subclasses must implement this method")
        

class InsertQuery(SqlQuery):
        
    # def render(self) -> str:
    #     sql = (
    #         f"INSERT INTO {self.fields.table_name} ({self.fields.build_insert_clause()})\n"
    #         f"VALUES ({self.fields.build_placeholders()})\n"
    #         f"RETURNING {self.fields.build_select_clause(False)}\n"
    #     )
    #     return sql
    def render(self) -> str:
        sql = (
            f"INSERT INTO {self.fields.table_name} ({self.fields.render_insert()})\n"
            f"VALUES ({self.fields.render_placeholders(start_idx=self._start_idx)})\n"
            f"RETURNING {self.render_fields(new_line=False)}\n"
        )
        return sql
    
    

class UpdateQuery(SqlQuery):
    
    def render(self) -> str:
        sql = (
            f"UPDATE {self.fields.table_name}\n"
            f"SET\n{self.indent(self.fields.render_insert())}\n"
            f"WHERE {self.fields.primary_key} = $1\n"
            f"RETURNING {self.fields.render_select(False)}\n"
        )
        return sql
    

    
    
class WithSubQuery(SqlContainer):
    
    
    def render(self) -> str:
        sql = "WITH "
        for idx, query in enumerate(self.queries):
            alias = query.alias or f"subquery_{idx}"
            sql += alias + " AS (\n" 
            sql += textwrap.indent(query.render(), "    ")
            sql += ")"
            sql += ", \n" if idx < len(self.queries) - 1 else "\n"
        return sql
    
    
    
class SelectQuery(SqlQuery):
    
    def render(self) -> str:
        sql = f"SELECT \n"
        sql += textwrap.indent(self.fields.render_select(), '    ')
        sql += f"\nFROM {self.fields.table_name}"
        if self.alias:
            sql += f"\nAS {self.alias}"
        sql += "\n"
        return sql
    
    
    
    
    