# pg_namespace.py

from typing import TYPE_CHECKING, Any, Optional, Type

from promptview.utils.db_connections import PGConnectionManager
from ..base.base_namespace import BaseNamespace
from .pg_field_info import PgFieldInfo
from .pg_relation import PgRelation


if TYPE_CHECKING:
    from promptview.model3.model3 import Model
    from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet




class PgNamespace(BaseNamespace["Model", PgFieldInfo]):
    
    def __init__(self, name: str, *fields: PgFieldInfo):
        super().__init__(name, db_type="postgres")
        for field in fields:
            self._register_field(field)

    def _register_field(self, field: PgFieldInfo):
        if field.is_primary_key:
            if self._primary_key:
                raise ValueError(f"Primary key already defined: {self._primary_key.name}")
            self._primary_key = field

        self.add_field(field)
        
        


    def __repr__(self):
        return f"<PgNamespace {self.name} fields={[f.name for f in self.iter_fields()]}>"

    def make_field_info(self, **kwargs) -> PgFieldInfo:
        enum_values = kwargs.get("enum_values")
        if enum_values and not kwargs.get("sql_type"):
            # consistent enum type name
            kwargs["sql_type"] = f"{self.name}_{kwargs['name']}_enum"
        return PgFieldInfo(**kwargs)



    async def insert(self, data: dict[str, Any]) -> dict[str, Any]:
        # 1. Handle relation fields...
        # for rel_name, relation in self._relations.items():
        #     if rel_name not in data or data[rel_name] is None:
        #         continue
        #     value = data[rel_name]
        #     if relation.is_one_to_one and isinstance(value, dict):
        #         related_ns = relation.foreign_cls.get_namespace()
        #         related_obj = await related_ns.insert(value)
        #         data[rel_name] = related_obj[related_ns.primary_key.name]
        #     elif relation.is_many_to_many and isinstance(value, list):
        #         related_ns = relation.foreign_cls.get_namespace()
        #         keys = []
        #         for v in value:
        #             if isinstance(v, dict):
        #                 rel_obj = await related_ns.insert(v)
        #                 keys.append(rel_obj[related_ns.primary_key.name])
        #             else:
        #                 keys.append(v)
        #         data[rel_name] = keys

        # 2. Usual insert logic
        fields = []
        placeholders = []
        values = []
        param_idx = 1

        for field in self.iter_fields():
            value = data.get(field.name, field.default)
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

        if not fields:
            sql = f'INSERT INTO "{self.name}" DEFAULT VALUES RETURNING *;'
            result = await PGConnectionManager.fetch_one(sql)
        else:
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

    def foreign_key_table_for(self, field):
        foreign_cls = getattr(field, "foreign_cls", None)
        if foreign_cls:
            return foreign_cls.get_namespace().name
        return None
        # raise ValueError(f"No foreign class for field {field.name} in {self.name}")
        return field.name.removesuffix("_id") + "s"


    
    async def create_namespace(self, dry_run: bool = False) -> str | None:
        """Creates the table and indexes but no foreign keys."""
        # Create Postgres enums first
        for field in self.iter_fields():
            if getattr(field, "enum_values", None):
                await self.create_enum(field.sql_type, field.enum_values)
        cols = []
        for field in self.iter_fields():
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
        return None
    
    
    async def create_enum(self, enum_name: str, enum_values: list[str]):
        enum_clause = ", ".join([f"'{v}'" for v in enum_values])
        query = f"""
            DO $$ 
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{enum_name}') THEN
                    CREATE TYPE {enum_name} AS ENUM ({enum_clause});
                END IF;
            END $$;
        """
        await PGConnectionManager.execute(query)


    async def add_foreign_keys(self, dry_run: bool = False) -> list[str]:
        """Adds all foreign key constraints after all tables exist."""
        sql_statements = []
        for field in self.iter_fields():
            if not field.is_foreign_key:
                continue
            constraint_name = f"{self.name}_{field.name}_fkey"
            check_sql = """
            SELECT 1 FROM pg_constraint WHERE conname = $1
            """
            exists = await PGConnectionManager.fetch_one(check_sql, constraint_name)
            if exists:
                continue
            ref_table = self.foreign_key_table_for(field)
            if ref_table is None:
                continue
            sql = f'''
                ALTER TABLE "{self.name}"
                ADD CONSTRAINT "{constraint_name}"
                FOREIGN KEY ("{field.name}")
                REFERENCES "{ref_table}" ("id")
                ON DELETE {field.on_delete}
                ON UPDATE {field.on_update};
            '''
            if dry_run:
                sql_statements.append(sql)
            else:
                await PGConnectionManager.execute(sql)
        return sql_statements

    
    async def drop_namespace(self, dry_run: bool = False) -> str | None:
        sql = f'DROP TABLE IF EXISTS "{self.name}" CASCADE;'
        if dry_run:
            return sql
        await PGConnectionManager.execute(sql)
        return None


    
    def query(self) -> "PgSelectQuerySet[Model]":
        from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
        return PgSelectQuerySet(self._model_cls)