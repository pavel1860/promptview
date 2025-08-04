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
        )

        self.sql_type = sql_type or self._resolve_sql_type()
        
    def get_placeholder(self, index: int) -> str:
        cast_types = {"UUID", "UUID[]", "INTEGER[]", "FLOAT[]", "TEXT[]", "BOOLEAN[]"}
        if self.sql_type in cast_types:
            return f"${index}::{self.sql_type}"
        return f"${index}"

    def _resolve_sql_type(self) -> str:
        dt = self.data_type
        if self.is_vector:
            return f"VECTOR({self.dimension})"
        if self.is_list:
            if dt == int: return "INTEGER[]"
            if dt == float: return "FLOAT[]"
            if dt == str: return "TEXT[]"
            if dt == bool: return "BOOLEAN[]"
            if dt == uuid.UUID: return "UUID[]"
        if dt == int: return "INTEGER"
        if dt == float: return "FLOAT"
        if dt == str: return "TEXT"
        if dt == bool: return "BOOLEAN"
        if dt == uuid.UUID: return "UUID"
        if dt == dict: return "JSONB"
        if inspect.isclass(dt) and issubclass(dt, BaseModel):
            return "JSONB"
        raise ValueError(f"Unsupported type: {dt}")

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
