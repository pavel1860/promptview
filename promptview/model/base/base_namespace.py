# base_namespace.py

from typing import Any, Dict, Generic, Optional, Type, TypeVar
import contextvars

from .base_field_info import BaseFieldInfo

MODEL = TypeVar("MODEL")
FIELD = TypeVar("FIELD", bound=BaseFieldInfo)


class BaseNamespace(Generic[MODEL, FIELD]):
    def __init__(self, name: str, db_type: str):
        self.name = name
        self.db_type = db_type
        self._fields: dict[str, FIELD] = {}
        self._model_cls: Optional[Type[MODEL]] = None
        self._ctx_model = contextvars.ContextVar(f"{name}_ctx", default=None)

    def set_model_class(self, model_cls: Type[MODEL]):
        self._model_cls = model_cls

    def add_field(self, field: FIELD):
        if field.name in self._fields:
            raise ValueError(f"Field {field.name} already exists in {self.name}")
        self._fields[field.name] = field

    def get_field(self, name: str) -> FIELD:
        return self._fields[name]

    def iter_fields(self):
        return self._fields.values()

    def get_field_names(self) -> list[str]:
        return list(self._fields.keys())

    def set_ctx(self, model: MODEL):
        self._ctx_model.set(model)

    def get_ctx(self) -> Optional[MODEL]:
        return self._ctx_model.get()

    def instantiate_model(self, data: dict[str, Any]) -> MODEL:
        if not self._model_cls:
            raise ValueError("Model class not set")
        return self._model_cls.from_dict(data)

    def validate_model_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        # Add foreign key default resolution here if needed
        return data

    def __repr__(self):
        return f"<BaseNamespace {self.name}>"
