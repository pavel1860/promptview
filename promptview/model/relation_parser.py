from typing import TYPE_CHECKING, Type, Dict, Any, get_origin, get_args, List
from pydantic.fields import FieldInfo
from promptview.model.base.base_namespace import BaseNamespace
from promptview.model.base.base_field_info import BaseFieldInfo



if TYPE_CHECKING:
    from promptview.model.relation_info import RelationInfo
    from promptview.model.model3 import Model


    


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
        from promptview.model.model3 import Model
        from promptview.model.relation_model import RelationModel

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

            related_cls = args[0] if is_list and args else annotation

            # No resolving yet — just store raw related_cls
            if isinstance(related_cls, type) and issubclass(related_cls, Model) and not issubclass(related_cls, RelationModel):
                rel_info = self.namespace.add_relation(
                    name=extra.get("name") or field_name,
                    primary_key=extra.get("primary_key", "id"),
                    foreign_key=extra.get("foreign_key", "id"),
                    foreign_cls=related_cls,
                    on_delete=extra.get("on_delete", "CASCADE"),
                    on_update=extra.get("on_update", "CASCADE"),
                    is_one_to_one=not is_list,
                    relation_model=None
                )
                self.relations[field_name] = rel_info

            elif isinstance(related_cls, type) and issubclass(related_cls, RelationModel):
                rel_info = self.namespace.add_relation(
                    name=extra.get("name") or field_name,
                    primary_key=extra.get("primary_key", "id"),
                    foreign_key=extra.get("foreign_key", "id"),
                    foreign_cls=extra.get("foreign_cls", related_cls),  # might still be unresolved
                    on_delete=extra.get("on_delete", "CASCADE"),
                    on_update=extra.get("on_update", "CASCADE"),
                    is_one_to_one=not is_list,
                    relation_model=related_cls
                )
                self.relations[field_name] = rel_info

            else:
                # Store unresolved (ForwardRef or str) for later resolution
                rel_info = self.namespace.add_relation(
                    name=extra.get("name") or field_name,
                    primary_key=extra.get("primary_key", "id"),
                    foreign_key=extra.get("foreign_key", "id"),
                    foreign_cls=related_cls,  # ForwardRef or str
                    on_delete=extra.get("on_delete", "CASCADE"),
                    on_update=extra.get("on_update", "CASCADE"),
                    is_one_to_one=not is_list,
                    relation_model=None
                )
                self.relations[field_name] = rel_info