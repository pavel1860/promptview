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
        keys = []
        placeholders = []
        values = []

        for idx, field in enumerate(self.iter_fields(), start=1):
            val = data.get(field.name, field.default)

            if val is None and not field.is_optional and not field.is_primary_key:
                raise ValueError(f"Missing required field: {field.name}")

            keys.append(f'"{field.name}"')
            placeholders.append(field.get_placeholder(idx))
            values.append(field.serialize(val))

        sql = (
            f'INSERT INTO "{self.name}" ({", ".join(keys)})\n'
            f'VALUES ({", ".join(placeholders)})\n'
            f'RETURNING *'
        )

        record = await PGConnectionManager.fetch_one(sql, *values)
        if record is None:
            raise RuntimeError("Insert failed, no record returned")
        return dict(record)


    
    async def get(self, id: Any) -> dict | None:
        sql = f'SELECT * FROM "{self.name}" WHERE "{self.primary_key.name}" = $1;'
        row = await PGConnectionManager.fetch_one(sql, id)
        return dict(row) if row else None

    
    async def delete(self, id: Any) -> dict | None:
        sql = f'DELETE FROM "{self.name}" WHERE "{self.primary_key.name}" = $1 RETURNING *;'
        row = await PGConnectionManager.fetch_one(sql, id)
        return dict(row) if row else None

    
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
        return None

    
    async def drop_namespace(self, dry_run: bool = False) -> str | None:
        sql = f'DROP TABLE IF EXISTS "{self.name}";'
        if dry_run:
            return sql
        await PGConnectionManager.execute(sql)
        return None

