# pg_relation.py

from typing import Type, Optional

class PgRelation:
    def __init__(
        self,
        name: str,
        primary_key: str,
        foreign_key: str,
        foreign_cls: Type,
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
        is_one_to_one: bool = False,
        is_many_to_many: bool = False,
        junction_cls: Optional[Type] = None,
        junction_keys: Optional[list[str]] = None,
    ):
        self.name = name
        self.primary_key = primary_key
        self.foreign_key = foreign_key
        self.foreign_cls = foreign_cls
        self.on_delete = on_delete
        self.on_update = on_update
        self.is_one_to_one = is_one_to_one
        self.is_many_to_many = is_many_to_many
        self.junction_cls = junction_cls
        self.junction_keys = junction_keys

    def __repr__(self):
        return (
            f"<PgRelation {self.name}: {self.primary_key}->{self.foreign_cls.__name__}.{self.foreign_key}>"
        )
