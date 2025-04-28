
import textwrap
from typing import Any, Self
from promptview.model2.postgres.fields_query import NamespaceQueryFields




def build_update_sql(fields: NamespaceQueryFields) -> str:
    sql = (
        f"UPDATE {fields.table_name}\n"
        f"SET\n{textwrap.indent(fields.build_insert_clause(), '    ')}\n"
        f"WHERE {fields.primary_key} = $1\n"
        f"RETURNING {fields.build_returning_clause()}\n"
    )
    return sql


def build_insert_sql(fields: NamespaceQueryFields) -> str:
    sql = (
        f"INSERT INTO {fields.table_name} ({fields.build_insert_clause()})\n"
        f"VALUES ({fields.build_placeholders()})\n"
        f"RETURNING {fields.build_returning_clause()}\n"
    )
    return sql



# def build_with_clause(queries: list[str]) -> str:
#     return "WITH " + ", ".join(queries) + " AS "




class SqlQuery:
    
    def __init__(self, fields: NamespaceQueryFields, alias: str | None = None):
        self.fields = fields
        self.alias = alias
    
    @property
    def inputs(self) -> list[Any]:
        return self.fields.inputs
    
    @property
    def outputs(self) -> list[Any]:
        return self.fields.outputs
    
    def render(self) -> str:
        raise NotImplementedError("Subclasses must implement this method")
    


class InsertQuery(SqlQuery):
        
    def render(self) -> str:
        sql = (
            f"INSERT INTO {self.fields.table_name} ({self.fields.build_insert_clause()})\n"
            f"VALUES ({self.fields.build_placeholders()})\n"
            f"RETURNING {self.fields.build_select_clause(False)}\n"
        )
        return sql
    
    

class UpdateQuery(SqlQuery):
    
    def render(self) -> str:
        sql = (
            f"UPDATE {self.fields.table_name}\n"
            f"SET\n{textwrap.indent(self.fields.build_insert_clause(), '    ')}\n"
            f"WHERE {self.fields.primary_key} = $1\n"
            f"RETURNING {self.fields.build_select_clause(False)}\n"
        )
        return sql
    

    
    
class WithSubQuery:
    
    
    def __init__(self, queries: list[SqlQuery]):
        self.queries = queries
    
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
        sql += textwrap.indent(self.fields.build_select_clause(), '    ')
        sql += f"\nFROM {self.fields.table_name}"
        if self.alias:
            sql += f"\nAS {self.alias}"
        sql += "\n"
        return sql
    
    
    
    
    