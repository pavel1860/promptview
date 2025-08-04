# qdrant_field_info.py

from typing import Any, Optional, Type

from promptview.model.base_namespace import Distance
from ..base.base_field_info import BaseFieldInfo


class QdrantFieldInfo(BaseFieldInfo):
    def __init__(
        self,
        name: str,
        field_type: Type[Any],
        is_primary_key: bool = False,
        is_vector: bool = False,
        dimension: Optional[int] = None,
        distance: Optional[Distance] = None,
        default: Any = None,
    ):
        super().__init__(name=name, field_type=field_type, default=default, is_primary_key=is_primary_key)
        self.is_vector = is_vector
        self.dimension = dimension
        self.distance = distance

        if is_vector and dimension is None:
            raise ValueError(f"Vector field '{name}' must have a dimension")
        if is_vector and distance is None:
            raise ValueError(f"Vector field '{name}' must specify a distance metric")

    def serialize(self, value: Any) -> Any:
        # Qdrant accepts Python-native values in payload
        return value

    def deserialize(self, value: Any) -> Any:
        return value

    def __repr__(self):
        base = f"QdrantFieldInfo(name={self.name}, type={self.data_type.__name__}"
        if self.is_vector:
            base += f", vector=True, dim={self.dimension}, distance={self.distance}"
        if self.is_primary_key:
            base += ", primary_key=True"
        return base + ")"
