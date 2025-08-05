from typing import TYPE_CHECKING, Type, Dict, Any, get_origin, get_args, List, Union
from pydantic.fields import FieldInfo
from .base.base_namespace import BaseNamespace
from .base.base_field_info import BaseFieldInfo

if TYPE_CHECKING:
    from promptview.model3.relation_info import RelationInfo
    from promptview.model3.model3 import Model


def get_relation_extras(field_info: FieldInfo) -> Dict[str, Any]:
    extra_json = field_info.json_schema_extra
    if isinstance(extra_json, dict):
        return dict(extra_json)
    return {}


class RelationParser:
    def __init__(self, model_cls: Type, namespace: BaseNamespace["Model", BaseFieldInfo]):
        self.model_cls = model_cls
        self.namespace = namespace
        self.relations: "Dict[str, RelationInfo]" = {}

    def parse(self):
        from promptview.model3.model3 import Model

        for field_name, field_info in self.model_cls.model_fields.items():
            if not isinstance(field_info, FieldInfo):
                continue

            extra = get_relation_extras(field_info)
            if not extra.get("is_relation", False):
                continue

            # --- 1) Unwrap Optional[T] / T | None ---
            annotation = field_info.annotation

            # Unwrap Optional[T] or T | None
            origin = get_origin(annotation)
            args = get_args(annotation)
            if origin is Union and type(None) in args:
                extra["is_optional"] = True
                annotation = next(a for a in args if a is not type(None))
            elif len(args) > 1 and type(None) in args:
                extra["is_optional"] = True
                annotation = next(a for a in args if a is not type(None))

            # Now detect if it's a list
            origin = get_origin(annotation)
            args = get_args(annotation)
            is_list = origin in (list, List)
            related_cls = args[0] if is_list and args else annotation

            junction_model = extra.get("junction_model")
            junction_keys = extra.get("junction_keys")

            # --- 3) Create the RelationInfo ---
            rel_info = self.namespace.add_relation(
                name=extra.get("name") or field_name,
                primary_key=extra.get("primary_key", "id"),
                foreign_key=extra.get("foreign_key", "id"),
                foreign_cls=related_cls,  # May be forward ref
                on_delete=extra.get("on_delete", "CASCADE"),
                on_update=extra.get("on_update", "CASCADE"),
                is_one_to_one=not is_list,
                relation_model=junction_model,
                junction_keys=junction_keys
            )
            self.relations[field_name] = rel_info

            # --- 4) Set reverse FK metadata ---
            if junction_model and junction_keys:
                # Many-to-Many
                junction_ns = junction_model.get_namespace()
                if len(junction_keys) >= 2:
                    # First key → current model
                    if junction_keys[0] in junction_ns._fields:
                        setattr(junction_ns._fields[junction_keys[0]], "foreign_cls", self.model_cls)
                    # Second key → related model
                    if junction_keys[1] in junction_ns._fields:
                        setattr(junction_ns._fields[junction_keys[1]], "foreign_cls", related_cls)
            else:
                # One-to-One or One-to-Many
                fk_name = extra.get("foreign_key", "id")
                # The FK belongs to the related model, not self.model_cls
                try:
                    fk_ns = related_cls.get_namespace()
                except Exception:
                    # related_cls might be a ForwardRef or str; skip for now
                    fk_ns = None
                if fk_ns and fk_name in fk_ns._fields:
                    setattr(fk_ns._fields[fk_name], "foreign_cls", self.model_cls)
