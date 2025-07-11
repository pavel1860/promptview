from typing import TYPE_CHECKING, Any, Literal
from promptview.block import block, Block
if TYPE_CHECKING:
    from promptview.model.postgres.namespace import PostgresNamespace, PgFieldInfo



@block()
def create_table_block_from_namespace(blk: Block, namespace: "PostgresNamespace"):
    with blk(f"CREATE TABLE IF NOT EXISTS {namespace.table_name}", style="func-col") as blk:
        for field in namespace.iter_fields():
            blk /= field.name, field.sql_type
            blk += "NULL" if field.is_optional or field.is_foreign_key else "NOT NULL"            



@block()
def create_table_block(blk: Block, name: str, *fields: "PgFieldInfo"):
    with blk(f"CREATE TABLE IF NOT EXISTS {name}", style="func-col") as blk:
        for field in fields:
            blk /= f'"{field.name}"', field.sql_type
            if field.is_primary_key:
                blk += "PRIMARY KEY"
                if field.sql_type == "UUID":
                    blk += "DEFAULT uuid_generate_v4()"
            else:
                # blk += "NULL" if field.is_optional and not field.is_foreign_key else "NOT NULL"            
                blk += "NULL" if field.is_optional else "NOT NULL"
            
