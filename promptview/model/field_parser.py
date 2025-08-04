# model/field_parser.py

from typing import Type, Any, Dict
from pydantic.fields import FieldInfo
from promptview.model.model3 import Model
from promptview.model.namespace_manager import NamespaceManager
from promptview.model.base.base_namespace import BaseNamespace
from promptview.model.base.base_field_info import BaseFieldInfo
from promptview.utils.string_utils import camel_to_snake

def get_field_extras(field_info: FieldInfo) -> Dict[str, Any]:
    """Extract extra metadata from a Pydantic FieldInfo."""
    extra_json = field_info.json_schema_extra
    if isinstance(extra_json, dict):
        return dict(extra_json)
    return {}

class FieldParser:
    def __init__(
        self, 
        model_cls: Type, 
        model_name: str, 
        db_type: str,
        namespace: BaseNamespace[Model, BaseFieldInfo],
        reserved_fields: set[str] | None = None
    ):
        self.model_cls = model_cls
        self.model_name = model_name
        self.db_type = db_type
        self.namespace = namespace
        self.reserved_fields = reserved_fields or set()
        self.field_extras: Dict[str, Dict[str, Any]] = {}

    def parse(self):
        """Parse and register scalar fields on the namespace."""
        for field_name, field_info in self.model_cls.model_fields.items():
            # Only process actual FieldInfo (skip relations/vectors)
            if not isinstance(field_info, FieldInfo):
                continue

            # Reserved field check
            if field_name in self.reserved_fields:
                raise ValueError(
                    f'Field "{field_name}" in model "{self.model_name}" is reserved. '
                    f'Reserved fields: {", ".join(self.reserved_fields)}'
                )
            
            extra = get_field_extras(field_info)
            self.field_extras[field_name] = extra

            # Only parse if not a relation or vector
            if extra.get("is_model_field", False) and not extra.get("is_relation", False) and not extra.get("is_vector", False):
                self._register_scalar_field(field_name, field_info, extra)

    def _register_scalar_field(self, field_name: str, field_info: FieldInfo, extra: Dict[str, Any]):
        """Register a scalar field with the namespace."""
        self.namespace.add_field(
            field_name,
            field_info.annotation,
            default=field_info.default,
            is_optional=extra.get("is_optional", False),
            foreign_key=extra.get("foreign_key", False),
            is_key=extra.get("is_key", False),
            is_vector=False,
            is_primary_key=extra.get("primary_key", False),
            is_default_temporal=extra.get("is_default_temporal", False),
        )

