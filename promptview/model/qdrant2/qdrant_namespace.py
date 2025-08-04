# qdrant_namespace.py

from ..base.base_namespace import BaseNamespace
from .qdrant_field_info import QdrantFieldInfo
from ..model import Model
from typing import Optional

class QdrantNamespace(BaseNamespace[Model, QdrantFieldInfo]):
    def __init__(self, name: str, *fields: QdrantFieldInfo):
        super().__init__(name, db_type="qdrant")
        self._primary_key: Optional[QdrantFieldInfo] = None

        for field in fields:
            self._register_field(field)

    def _register_field(self, field: QdrantFieldInfo):
        if field.is_primary_key:
            if self._primary_key:
                raise ValueError(f"Primary key already defined: {self._primary_key.name}")
            self._primary_key = field
        self.add_field(field)

    @property
    def primary_key(self) -> QdrantFieldInfo:
        if not self._primary_key:
            raise ValueError(f"No primary key defined for Qdrant namespace '{self.name}'")
        return self._primary_key

    def __repr__(self):
        return f"<QdrantNamespace {self.name} fields={[f.name for f in self.iter_fields()]}>"
