# pg_namespace.py

from typing import Any, Optional, Type

from promptview.utils.db_connections import PGConnectionManager
from ..base.base_namespace import BaseNamespace
from .pg_field_info import PgFieldInfo
from ..model import Model  # Assuming all models inherit from this base
from .pg_relation import PgRelation

class PgNamespace(BaseNamespace[Model, PgFieldInfo]):
    
    def __init__(self, name: str, *fields: PgFieldInfo):
        super().__init__(name, db_type="postgres")
        self._primary_key: Optional[PgFieldInfo] = None
        self._relations: dict[str, PgRelation] = {}
        for field in fields:
            self._register_field(field)

    def _register_field(self, field: PgFieldInfo):
        if field.is_primary_key:
            if self._primary_key:
                raise ValueError(f"Primary key already defined: {self._primary_key.name}")
            self._primary_key = field

        self.add_field(field)
        
        
    def add_relation(
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
    ) -> PgRelation:
        rel = PgRelation(
            name=name,
            primary_key=primary_key,
            foreign_key=foreign_key,
            foreign_cls=foreign_cls,
            on_delete=on_delete,
            on_update=on_update,
            is_one_to_one=is_one_to_one,
            is_many_to_many=is_many_to_many,
            junction_cls=junction_cls,
            junction_keys=junction_keys,
        )
        self._relations[name] = rel
        return rel

    def get_relation(self, name: str) -> Optional[PgRelation]:
        return self._relations.get(name)

    @property
    def primary_key(self) -> PgFieldInfo:
        if self._primary_key is None:
            raise ValueError(f"No primary key defined for namespace '{self.name}'")
        return self._primary_key

    def __repr__(self):
        return f"<PgNamespace {self.name} fields={[f.name for f in self.iter_fields()]}>"

    def make_field_info(self, **kwargs) -> PgFieldInfo:
        return PgFieldInfo(**kwargs)

    # async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
    #     fields = []
    #     placeholders = []
    #     values = []

    #     for idx, field in enumerate(self.iter_fields(), start=1):
    #         value = data.get(field.name, field.default)

    #         if value is None:
    #             if not field.is_optional and not field.is_primary_key:
    #                 raise ValueError(f"Missing required field: {field.name}")
    #         serialized = field.serialize(value)
    #         fields.append(f'"{field.name}"')
    #         placeholders.append(field.get_placeholder(idx))
    #         values.append(serialized)

    #     sql = f"""
    #     INSERT INTO "{self.name}" ({", ".join(fields)})
    #     VALUES ({", ".join(placeholders)})
    #     RETURNING *;
    #     """

    #     result = await PGConnectionManager.fetch_one(sql, *values)
    #     if not result:
    #         raise RuntimeError("Insert failed, no row returned")
    #     return dict(result)
    
    # In pg_namespace.py

    async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
        # 1. Handle relation fields: if present and is dict/list, insert related model(s)
        for rel_name, relation in self._relations.items():
            if rel_name not in data or data[rel_name] is None:
                continue
            value = data[rel_name]
            # Support for one-to-one or many-to-one
            if relation.is_one_to_one and isinstance(value, dict):
                related_ns = relation.foreign_cls.get_namespace()
                related_obj = await related_ns.insert(value)
                data[rel_name] = related_obj[related_ns.primary_key.name]
            # Support for many-to-many (list of dicts)
            elif relation.is_many_to_many and isinstance(value, list):
                related_ns = relation.foreign_cls.get_namespace()
                keys = []
                for v in value:
                    if isinstance(v, dict):
                        rel_obj = await related_ns.insert(v)
                        keys.append(rel_obj[related_ns.primary_key.name])
                    else:
                        keys.append(v)  # Already an ID
                data[rel_name] = keys
            # else: treat as ID already present

        # 2. Usual insert logic
        fields = []
        placeholders = []
        values = []
        param_idx = 1

        for field in self.iter_fields():
            value = data.get(field.name, field.default)
            # NEW: Skip PK if value is None (let PG assign)
            if field.is_primary_key and value is None:
                continue

            if value is None:
                if not field.is_optional and not field.is_primary_key:
                    raise ValueError(f"Missing required field: {field.name}")
            serialized = field.serialize(value)
            fields.append(f'"{field.name}"')
            placeholders.append(field.get_placeholder(param_idx))
            values.append(serialized)
            param_idx += 1


        sql = f"""
        INSERT INTO "{self.name}" ({", ".join(fields)})
        VALUES ({", ".join(placeholders)})
        RETURNING *;
        """

        result = await PGConnectionManager.fetch_one(sql, *values)
        if not result:
            raise RuntimeError("Insert failed, no row returned")
        return dict(result)

    
    
    
    async def update(self, id: Any, data: dict[str, Any]) -> dict[str, Any]:
        set_clauses = []
        values = []

        index = 1
        for field in self.iter_fields():
            if field.is_primary_key:
                continue  # primary key goes in WHERE clause
            if field.name not in data:
                continue

            value = data[field.name]
            serialized = field.serialize(value)
            placeholder = field.get_placeholder(index)
            set_clauses.append(f'"{field.name}" = {placeholder}')
            values.append(serialized)
            index += 1

        # WHERE clause for primary key
        pk_field = self.primary_key
        where_placeholder = f"${index}"
        set_clause = ", ".join(set_clauses)
        values.append(pk_field.serialize(id))

        sql = f"""
        UPDATE "{self.name}"
        SET {set_clause}
        WHERE "{pk_field.name}" = {where_placeholder}
        RETURNING *;
        """

        result = await PGConnectionManager.fetch_one(sql, *values)
        if not result:
            raise RuntimeError("Update failed, no row returned")
        return dict(result)



    
    async def get(self, id: Any) -> dict[str, Any] | None:
        pk_field = self.primary_key
        sql = f'SELECT * FROM "{self.name}" WHERE "{pk_field.name}" = $1'
        result = await PGConnectionManager.fetch_one(sql, id)
        return dict(result) if result else None


    
    async def delete(self, id: Any) -> dict[str, Any] | None:
        pk_field = self.primary_key
        sql = f'DELETE FROM "{self.name}" WHERE "{pk_field.name}" = $1 RETURNING *'
        result = await PGConnectionManager.fetch_one(sql, id)
        return dict(result) if result else None

    def foreign_key_table_for(self, field: PgFieldInfo) -> str:
        # naive convention-based resolution, e.g. conv_id → "conversations"
        return field.name.removesuffix("_id") + "s"

    
    async def create_namespace(self, dry_run: bool = False) -> str | None:
        cols = []
        for field in self.iter_fields():
            # Use SERIAL or IDENTITY for int primary key
            if field.is_primary_key:
                if field.field_type == int:
                    col_def = f'"{field.name}" SERIAL PRIMARY KEY'
                else:
                    col_def = f'"{field.name}" {field.sql_type} PRIMARY KEY'
            else:
                col_def = f'"{field.name}" {field.sql_type}'
            cols.append(col_def)
        cols = ",\n  ".join(cols)
        sql = f'CREATE TABLE IF NOT EXISTS "{self.name}" (\n  {cols}\n);'

        if dry_run:
            return sql
        await PGConnectionManager.execute(sql)
        for field in self.iter_fields():
            if field.index:
                index_name = f"{self.name}_{field.name}_idx"
                sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{self.name}" ("{field.name}");'
                await PGConnectionManager.execute(sql)
                
        for field in self.iter_fields():
            if field.is_foreign_key:
                constraint_name = f"{self.name}_{field.name}_fkey"

                check_sql = """
                SELECT 1
                FROM pg_constraint
                WHERE conname = $1
                """
                exists = await PGConnectionManager.fetch_one(check_sql, constraint_name)
                if exists:
                    continue  # skip adding the FK, it's already there

                ref_table = self.foreign_key_table_for(field)
                sql = f'''
                    ALTER TABLE "{self.name}"
                    ADD CONSTRAINT "{constraint_name}"
                    FOREIGN KEY ("{field.name}")
                    REFERENCES "{ref_table}" ("id")
                    ON DELETE {field.on_delete}
                    ON UPDATE {field.on_update};
                '''
                await PGConnectionManager.execute(sql)

        return None

    
    async def drop_namespace(self, dry_run: bool = False) -> str | None:
        sql = f'DROP TABLE IF EXISTS "{self.name}" CASCADE;'
        if dry_run:
            return sql
        await PGConnectionManager.execute(sql)
        return None

