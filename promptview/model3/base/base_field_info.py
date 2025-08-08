# base_field_info.py

from typing import Any, List, Type, Optional, get_args, get_origin
import uuid

class BaseFieldInfo:
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
        index: bool = False,
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
        enum_values: Optional[List[str]] = None,
        order_by: bool = False,
        foreign_cls: Optional[Type] = None,
    ):
        self.name = name
        self.field_type = field_type
        self.default = default
        self.is_optional = is_optional
        self.is_primary_key = is_primary_key
        self.is_foreign_key = is_foreign_key
        self.is_vector = is_vector
        self.dimension = dimension
        self.is_key = is_key or is_primary_key
        self.index = index
        self.on_delete = on_delete
        self.on_update = on_update
        self.enum_values = enum_values
        self.order_by = order_by
        self.foreign_cls = foreign_cls
        # For key fields (uuid or int)
        if self.is_key:
            self.key_type = "uuid" if field_type is uuid.UUID else "int"

        # Detect list fields
        self.is_list = get_origin(field_type) in (list, List)
        self.data_type = get_args(field_type)[0] if self.is_list else field_type

    def serialize(self, value: Any) -> Any:
        return value

    def deserialize(self, value: Any) -> Any:
        return value
