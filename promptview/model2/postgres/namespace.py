from typing import Any, Literal, Type
from pydantic import BaseModel
from pydantic.fields import FieldInfo
# from promptview.model2.clients.postgres.builder import build_create_table_sql
from promptview.model2.postgres.builder import SQLBuilder
from promptview.utils.model_utils import get_list_type, is_list_type
from promptview.model2.base_namespace import Namespace, NSFieldInfo
from promptview.utils.db_connections import PGConnectionManager
import datetime as dt

PgIndexType = Literal["btree", "hash", "gin", "gist", "spgist", "brin"]


class PgFieldInfo(NSFieldInfo[PgIndexType]):
    pass




class PostgresNamespace(Namespace):
    
    
    def __init__(self, name: str):
        super().__init__(name)
        
    @property
    def table_name(self) -> str:
        return self.name
        
    def add_field(
        self, 
        name: str, 
        field_type: type[Any],
        extra: dict[str, Any] | None = None,
    ):
        """
        Add a field to the namespace.
        """
        db_field_type = SQLBuilder.map_field_to_sql_type(field_type, extra)

        self._fields[name] = PgFieldInfo(
            name=name,
            field_type=field_type,
            db_field_type=db_field_type,
            index=None,
            extra=None,
        )
        
    def add_relation(
        self, 
        name: str, 
        field_info: FieldInfo,
    ):
        pass


    async def create_namespace(self):
        res = await SQLBuilder.create_table(self)
        return res
        

    async def drop_namespace(self):
        res = await SQLBuilder.drop_table(self)
        return res
        

    
    
        
        