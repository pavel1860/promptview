# model/relation_parser.py

from typing import Type, Dict, Any
from pydantic.fields import FieldInfo
from promptview.model.base.base_namespace import BaseNamespace
from promptview.model.model3 import Model
from promptview.model.base.base_field_info import BaseFieldInfo
from typing import get_origin, get_args

def get_relation_extras(field_info: FieldInfo) -> Dict[str, Any]:
    extra_json = field_info.json_schema_extra
    if isinstance(extra_json, dict):
        return dict(extra_json)
    return {}

class RelationParser:
    def __init__(self, model_cls: Type, namespace: BaseNamespace[Model, BaseFieldInfo]):
        self.model_cls = model_cls
        self.namespace = namespace
        self.relations: Dict[str, Any] = {}

    def parse(self):
        """Parse and register relation fields on the namespace."""
        for field_name, field_info in self.model_cls.model_fields.items():
            if not isinstance(field_info, FieldInfo):
                continue

            extra = get_relation_extras(field_info)
            if not extra.get("is_relation", False):
                continue  # Not a relation, skip

            # Determine relation type: one-to-one, one-to-many, many-to-many, etc.
            # For now, only scaffold logic
            rel_type = extra.get("relation_type", "one_to_one")  # or parse from annotation

            if rel_type == "one_to_one":
                self._register_one_to_one(field_name, field_info, extra)
            elif rel_type == "one_to_many":
                self._register_one_to_many(field_name, field_info, extra)
            elif rel_type == "many_to_many":
                self._register_many_to_many(field_name, field_info, extra)
            else:
                raise ValueError(f"Unknown relation type '{rel_type}' for field '{field_name}'")

    def _register_one_to_one(self, field_name: str, field_info: FieldInfo, extra: Dict[str, Any]):
        foreign_cls = self._get_related_model(field_info.annotation)
        rel = self.namespace.add_relation(
            name=field_name,
            primary_key=extra.get("primary_key", "id"),
            foreign_key=extra.get("foreign_key", "id"),
            foreign_cls=foreign_cls,
            on_delete=extra.get("on_delete", "CASCADE"),
            on_update=extra.get("on_update", "CASCADE"),
            is_one_to_one=True
        )
        self.relations[field_name] = rel

    def _register_one_to_many(self, field_name: str, field_info: FieldInfo, extra: Dict[str, Any]):
        foreign_cls = self._get_related_model(field_info.annotation)
        rel = self.namespace.add_relation(
            name=field_name,
            primary_key=extra.get("primary_key", "id"),
            foreign_key=extra.get("foreign_key", "id"),
            foreign_cls=foreign_cls,
            on_delete=extra.get("on_delete", "CASCADE"),
            on_update=extra.get("on_update", "CASCADE"),
            is_one_to_one=False
        )
        self.relations[field_name] = rel

    def _register_many_to_many(self, field_name: str, field_info: FieldInfo, extra: Dict[str, Any]):
        foreign_cls = self._get_related_model(field_info.annotation)
        junction_cls = extra.get("junction_model", None)
        junction_keys = extra.get("junction_keys", None)
        if not junction_cls or not junction_keys:
            raise ValueError(f"Many-to-many relation '{field_name}' requires 'junction_model' and 'junction_keys'.")
        rel = self.namespace.add_many_relation(
            name=field_name,
            primary_key=extra.get("primary_key", "id"),
            foreign_key=extra.get("foreign_key", "id"),
            foreign_cls=foreign_cls,
            junction_cls=junction_cls,
            junction_keys=junction_keys,
            on_delete=extra.get("on_delete", "CASCADE"),
            on_update=extra.get("on_update", "CASCADE"),
        )
        self.relations[field_name] = rel

    def _get_related_model(self, annotation):
        """Extract model class from annotation (e.g., Relation[User])"""
        origin = get_origin(annotation)
        args = get_args(annotation)
        if args:
            return args[0]  # For Relation[OtherModel]
        return annotation   # For direct class use

