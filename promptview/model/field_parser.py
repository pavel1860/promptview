# model/field_parser.py

from typing import TYPE_CHECKING, Type, Any, Dict
from pydantic.fields import FieldInfo

from promptview.model.namespace_manager import NamespaceManager
from promptview.model.base.base_namespace import BaseNamespace
from promptview.model.base.base_field_info import BaseFieldInfo
from promptview.model.util import unpack_extra
from promptview.utils.string_utils import camel_to_snake

if TYPE_CHECKING:
    from promptview.model.model3 import Model

def get_field_extras(field_info: FieldInfo) -> Dict[str, Any]:
    """Extract extra metadata from a Pydantic FieldInfo."""
    extra_json = field_info.json_schema_extra
    if isinstance(extra_json, dict):
        return dict(extra_json)
    return {}

class FieldParser:
    def __init__(self, model_cls, model_name, db_type, namespace, reserved_fields=None):
        self.model_cls = model_cls
        self.model_name = model_name
        self.db_type = db_type
        self.namespace = namespace
        self.reserved_fields = reserved_fields or set()
        self.field_extras = {}

    def parse(self):
        for field_name, field_info in self.model_cls.model_fields.items():
            extra = unpack_extra(field_info)
            self.field_extras[field_name] = extra

            # Skip relations & vectors here
            if not extra.get("is_model_field", False):
                continue
            if extra.get("is_relation", False) or extra.get("is_vector", False):
                continue

            self._register_scalar_field(field_name, field_info, extra)

    def _register_scalar_field(self, field_name, field_info, extra):
        # Build backend-specific FieldInfo via namespace
        field_obj = self.namespace.make_field_info(
            name=field_name,
            field_type=field_info.annotation,
            default=field_info.default,
            is_optional=extra.get("is_optional", False),
            is_primary_key=extra.get("primary_key", False),
            is_foreign_key=extra.get("foreign_key", False),
            is_vector=False,
            index=extra.get("index", False),
            on_delete=extra.get("on_delete", "CASCADE"),
            on_update=extra.get("on_update", "CASCADE"),
        )
        self.namespace.add_field(field_obj)
