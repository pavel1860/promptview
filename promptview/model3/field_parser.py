# model/field_parser.py

from typing import TYPE_CHECKING, Type, Any, Dict, Union, get_args, get_origin
from pydantic.fields import FieldInfo
from promptview.model.util import unpack_extra


if TYPE_CHECKING:
    from promptview.model3.model3 import Model

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

            # Detect Optional[T] or T | None
            annotation = field_info.annotation
            origin = get_origin(annotation)
            args = get_args(annotation)
            if origin is Union and type(None) in args:
                extra["is_optional"] = True
                field_type = next(a for a in args if a is not type(None))
            elif len(args) > 1 and type(None) in args:
                extra["is_optional"] = True
                field_type = next(a for a in args if a is not type(None))
            else:
                field_type = annotation

            self.field_extras[field_name] = extra

            if extra.get("is_relation", False) or extra.get("is_vector", False):
                continue

            self._register_scalar_field(field_name, field_type, field_info, extra)

    def _register_scalar_field(self, field_name, field_type, field_info, extra):
        # Build backend-specific FieldInfo via namespace
        field_obj = self.namespace.make_field_info(
            name=field_name,
            field_type=field_type,
            default=field_info.default,
            is_optional=extra.get("is_optional", False),
            is_primary_key=extra.get("primary_key", False),
            is_foreign_key=extra.get("foreign_key", False),
            is_vector=False,
            index=extra.get("index", False),
            on_delete=extra.get("on_delete", "CASCADE"),
            on_update=extra.get("on_update", "CASCADE"),
            junction_keys=extra.get("junction_keys", None)
        )
        self.namespace.add_field(field_obj)
