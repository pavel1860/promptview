# promptview/model/base/relation_info.py
from typing import TYPE_CHECKING, Any, Optional, Type, ForwardRef

if TYPE_CHECKING:
    from promptview.model3.model3 import Model

class RelationInfo:
    def __init__(
        self,
        name: str,
        primary_key: str,
        foreign_key: str,
        primary_cls: Type["Model"],
        foreign_cls: Any,  # may be a type, str, or ForwardRef
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
        is_one_to_one: bool = False,
        relation_model: Optional[Type["Model"]] = None
    ):
        self.name = name
        self.primary_key = primary_key
        self.foreign_key = foreign_key
        self.primary_cls = primary_cls
        self._foreign_cls_raw = foreign_cls
        self._foreign_cls_resolved: Optional[Type["Model"]] = (
            foreign_cls if isinstance(foreign_cls, type) else None
        )
        self.on_delete = on_delete
        self.on_update = on_update
        self.is_one_to_one = is_one_to_one
        self.relation_model = relation_model

    @property
    def foreign_cls(self) -> Type["Model"]:
        if self._foreign_cls_resolved is None:
            raise RuntimeError(
                f"Relation '{self.name}' target model not resolved yet"
            )
        return self._foreign_cls_resolved

    @property
    def is_many_to_many(self) -> bool:
        return self.relation_model is not None

    def resolve_foreign_cls(self, globalns: dict[str, Any]):
        from typing import ForwardRef
        import typing
        if self._foreign_cls_resolved:
            return
        raw = self._foreign_cls_raw
        if isinstance(raw, ForwardRef):
            self._foreign_cls_resolved = raw._evaluate(globalns, None, set())
        elif isinstance(raw, str):
            self._foreign_cls_resolved = typing.ForwardRef(raw)._evaluate(globalns, None, set())
        elif isinstance(raw, type):
            self._foreign_cls_resolved = raw
        else:
            raise ValueError(f"Cannot resolve foreign_cls for relation '{self.name}'")
