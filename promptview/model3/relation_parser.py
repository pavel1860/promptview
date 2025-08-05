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

            annotation = field_info.annotation
            origin = get_origin(annotation)
            args = get_args(annotation)
            is_list = origin in (list, List)

            # The related model is always the element type for List[T] or direct type T
            related_cls = args[0] if is_list and args else annotation
            junction_model = extra.get("junction_model")  # For M:N

            # --- Create the RelationInfo ---
            rel_info = self.namespace.add_relation(
                name=extra.get("name") or field_name,
                primary_key=extra.get("primary_key", "id"),
                foreign_key=extra.get("foreign_key", "id"),
                foreign_cls=related_cls,  # Actual target model (may be forward ref)
                on_delete=extra.get("on_delete", "CASCADE"),
                on_update=extra.get("on_update", "CASCADE"),
                is_one_to_one=not is_list,
                relation_model=junction_model,
                junction_keys=extra.get("junction_keys")
            )
            self.relations[field_name] = rel_info

            # --- Attach reverse FK metadata ---
            if junction_model and extra.get("junction_keys"):
                # Many-to-Many: attach to junction model FKs
                junction_ns = junction_model.get_namespace()
                keys = extra["junction_keys"]

                if len(keys) >= 2:
                    # First key → current model
                    if keys[0] in junction_ns._fields:
                        setattr(junction_ns._fields[keys[0]], "foreign_cls", self.model_cls)
                    # Second key → related (target) model
                    if keys[1] in junction_ns._fields:
                        setattr(junction_ns._fields[keys[1]], "foreign_cls", related_cls)

            else:
                # One-to-One or One-to-Many: attach to FK field in the referencing model
                fk_name = extra.get("foreign_key", "id")
                ns = self.model_cls.get_namespace()
                if fk_name in ns._fields:
                    setattr(ns._fields[fk_name], "foreign_cls", related_cls)
