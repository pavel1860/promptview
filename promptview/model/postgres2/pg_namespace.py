# pg_namespace.py

from typing import Any, Optional, Type

from promptview.utils.db_connections import PGConnectionManager
from ..base.base_namespace import BaseNamespace
from .pg_field_info import PgFieldInfo
from ..model import Model  # Assuming all models inherit from this base

class PgNamespace(BaseNamespace[Model, PgFieldInfo]):
    
    def __init__(self, name: str, *fields: PgFieldInfo):
        super().__init__(name, db_type="postgres")
        self._primary_key: Optional[PgFieldInfo] = None

        for field in fields:
            self._register_field(field)

    def _register_field(self, field: PgFieldInfo):
        if field.is_primary_key:
            if self._primary_key:
                raise ValueError(f"Primary key already defined: {self._primary_key.name}")
            self._primary_key = field

        self.add_field(field)

    @property
    def primary_key(self) -> PgFieldInfo:
        if self._primary_key is None:
            raise ValueError(f"No primary key defined for namespace '{self.name}'")
        return self._primary_key

    def __repr__(self):
        return f"<PgNamespace {self.name} fields={[f.name for f in self.iter_fields()]}>"



    async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
        fields = []
        placeholders = []
        values = []

        for idx, field in enumerate(self.iter_fields(), start=1):
            value = data.get(field.name, field.default)

            if value is None:
                if not field.is_optional and not field.is_primary_key:
                    raise ValueError(f"Missing required field: {field.name}")
            serialized = field.serialize(value)
            fields.append(f'"{field.name}"')
            placeholders.append(field.get_placeholder(idx))
            values.append(serialized)

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
            col_def = f'"{field.name}" {field.sql_type}'
            if field.is_primary_key:
                col_def += " PRIMARY KEY"
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
                ref_table = self.foreign_key_table_for(field)
                sql = f'''
                    ALTER TABLE "{self.name}"
                    ADD CONSTRAINT "{self.name}_{field.name}_fkey"
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

