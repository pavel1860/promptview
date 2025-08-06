# pg_field_info.py

import inspect

from pydantic import BaseModel
from ..base.base_field_info import BaseFieldInfo
from typing import Any, List, Optional, Type
import uuid
import datetime as dt
import json
from typing import get_origin, get_args, Union
import uuid

class PgFieldInfo(BaseFieldInfo):
    def __init__(
        self,
        name: str,
        field_type: Type,
        *,
        default: Any = None,
        is_optional: bool = False,
        is_primary_key: bool = False,
        is_foreign_key: bool = False,
        is_vector: bool = False,
        dimension: Optional[int] = None,
        is_key: bool = False,
        sql_type: Optional[str] = None,  # Allow override
        index: bool = False,
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
        enum_values: Optional[List[str]] = None,
        order_by: bool = False,
    ):
        super().__init__(
            name=name,
            field_type=field_type,
            default=default,
            is_optional=is_optional,
            is_primary_key=is_primary_key,
            is_foreign_key=is_foreign_key,
            is_vector=is_vector,
            dimension=dimension,
            is_key=is_key,
            index=index,
            on_delete=on_delete,
            on_update=on_update,
            enum_values=enum_values,
            order_by=order_by,
        )

        self.sql_type = sql_type or self._resolve_sql_type()
        
    def get_placeholder(self, index: int) -> str:
        cast_types = {"UUID", "UUID[]", "INTEGER[]", "FLOAT[]", "TEXT[]", "BOOLEAN[]"}
        if self.sql_type in cast_types:
            return f"${index}::{self.sql_type}"
        return f"${index}"

    def _resolve_sql_type(self) -> str:
        py_type = self.data_type
        if self.is_vector:
            return f"VECTOR({self.dimension})"
        if getattr(self, "enum_values", None):
            return f"{self.name}_enum"  # enum type name from create_enum()
        if self.is_list:
            if py_type == int: return "INTEGER[]"
            if py_type == float: return "FLOAT[]"
            if py_type == str: return "TEXT[]"
            if py_type == bool: return "BOOLEAN[]"
            if py_type == uuid.UUID: return "UUID[]"
        if py_type == int: return "INTEGER"
        if py_type == float: return "FLOAT"
        if py_type == str: return "TEXT"
        if py_type == bool: return "BOOLEAN"
        if py_type == uuid.UUID: return "UUID"
        if py_type == dict: return "JSONB"
        if py_type == dt.datetime: return "TIMESTAMP"
        if py_type == dt.date: return "DATE"
        if inspect.isclass(py_type) and issubclass(py_type, BaseModel):
            return "JSONB"
        raise ValueError(f"Unsupported type: {py_type}")

    def serialize(self, value: Any) -> Any:
        """Serialize the value for the database"""

        if value is None:
            return self.default

        # Auto-generate UUID key
        if self.is_key and self.key_type == "uuid" and value is None:
            return str(uuid.uuid4())

        # Vector field
        if self.is_vector:
            return f"[{', '.join(map(str, value))}]"

        # JSONB handling
        if self.sql_type == "JSONB":
            if self.is_list:
                value = [make_json_serializable(v) if isinstance(v, dict) else v for v in value]
                return json.dumps(value)

            if self.data_type is dict or (inspect.isclass(self.data_type) and issubclass(self.data_type, BaseModel)):
                if isinstance(value, Serializable):
                    return json.dumps(value.serialize())
                return json.dumps(make_json_serializable(value))

        return value


    def deserialize(self, value: Any) -> Any:
        if self.field_type == uuid.UUID and isinstance(value, str):
            return uuid.UUID(value)
        return value
