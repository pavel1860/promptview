

from typing import TYPE_CHECKING, Any
from promptview.utils.db_connections import PGConnectionManager
from promptview.utils.model_utils import get_list_type, is_list_type
import datetime as dt
from pydantic import BaseModel

if TYPE_CHECKING:
    from promptview.model2.postgres.namespace import PostgresNamespace



class SQLBuilder:

    @classmethod
    async def execute(cls, sql: str):
        try:
            res = await PGConnectionManager.execute(sql)
            return res
        except Exception as e:
            print(sql)
            raise e

    @classmethod
    async def fetch(cls, sql: str):
        try:
            res = await PGConnectionManager.fetch(sql)
            return res
        except Exception as e:
            print(sql)
            raise e

    @classmethod
    def map_field_to_sql_type(cls, field_type: type[Any], extra: dict[str, Any] | None = None) -> str:
        if is_list_type(field_type):
            list_type = get_list_type(field_type)
            if isinstance(list_type, int):                
                db_field_type = "INTEGER[]"
            elif isinstance(list_type, float):
                db_field_type = "FLOAT[]"
            elif isinstance(list_type, str): 
                db_field_type = "TEXT[]"
            # elif isinstance(list_type, Model):
            #     partition = field.json_schema_extra.get("partition")
            #     create_table_sql += f'"{field_name}" UUID FOREIGN KEY REFERENCES {model_to_table_name(field_type)} ("{partition}")'
            else:
                raise ValueError(f"Unsupported list type: {list_type}")
        else:
            if extra and extra.get("db_type"):
                custom_type = extra.get("db_type")
                if type(custom_type) != str:
                    raise ValueError(f"Custom type is not a string: {custom_type}")
                db_field_type = custom_type                
            elif field_type == bool:
                db_field_type = "BOOLEAN"
            elif field_type == int:
                db_field_type = "INTEGER"
            elif field_type == float:
                db_field_type = "FLOAT"
            elif field_type == str:
                db_field_type = "TEXT"
            elif field_type == dt.datetime:
                # TODO: sql_type = "TIMESTAMP WITH TIME ZONE"
                db_field_type = "TIMESTAMP"
            elif isinstance(field_type, dict) or (isinstance(field_type, type) and issubclass(field_type, BaseModel)):
                db_field_type = "JSONB"
            else:
                raise ValueError(f"Unsupported field type: {field_type}")
        return db_field_type



    @classmethod
    async def create_table(cls, namespace: "PostgresNamespace") -> str:
        sql = f"CREATE TABLE IF NOT EXISTS {namespace.name} (\n"
        
        for field in namespace.iter_fields():
            sql += f"{field.name} {field.db_field_type}"
            sql += ",\n"
        sql = sql[:-2]
        sql += ")"
        return await cls.execute(sql)



    @classmethod
    async def drop_table(cls, namespace: "PostgresNamespace") -> str:
        sql = f"DROP TABLE IF EXISTS {namespace.table_name}"
        return await cls.execute(sql)
    
    
    @classmethod
    async def drop_many_tables(cls, table_names: list[str]) -> None:
        sql = f"DROP TABLE IF EXISTS {', '.join(table_names)}"
        await cls.execute(sql)


    @classmethod
    async def get_tables(cls, schema: str | None = "public") -> list[str]:
        sql = "SELECT table_name FROM information_schema.tables"
        if schema:
            sql += f" WHERE table_schema='{schema}'"
        res = await cls.fetch(sql)
        return [row["table_name"] for row in res]








