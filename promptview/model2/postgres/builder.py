

from enum import Enum
import inspect
from typing import TYPE_CHECKING, Any, Literal
from promptview.utils.db_connections import PGConnectionManager, SyncPGConnectionManager
from promptview.utils.model_utils import get_list_type, is_list_type
import datetime as dt
from pydantic import BaseModel

if TYPE_CHECKING:
    from promptview.model2.postgres.namespace import PostgresNamespace, PgFieldInfo



class SQLBuilder:
    """SQL builder for PostgreSQL"""

    # PostgreSQL type constants
    
    
    @classmethod
    def execute(cls, sql: str):
        """Execute a SQL statement"""
        try:
            res = SyncPGConnectionManager.execute(sql)
            return res
        except Exception as e:
            print(sql)
            raise e

    @classmethod
    async def fetch(cls, sql: str):
        """Fetch results from a SQL query"""
        try:
            res = await PGConnectionManager.fetch(sql)
            return res
        except Exception as e:
            print(sql)
            raise e
        
    # @classmethod
    # async def initialize_versioning(cls):
    #     """Initialize versioning tables"""
    #     await PGConnectionManager.initialize()
    #     # Create required tables
    #     await PGConnectionManager.execute("""
    #     CREATE TABLE IF NOT EXISTS branches (
    #         id SERIAL PRIMARY KEY,
    #         name TEXT,
    #         created_at TIMESTAMP DEFAULT NOW(),
    #         updated_at TIMESTAMP DEFAULT NOW(),
    #         forked_from_turn_index INTEGER,
    #         forked_from_branch_id INTEGER,
    #         current_index INTEGER DEFAULT 0,
    #         FOREIGN KEY (forked_from_branch_id) REFERENCES branches(id)
    #     );

    #     CREATE TABLE IF NOT EXISTS turns (
    #         id SERIAL PRIMARY KEY,
    #         created_at TIMESTAMP DEFAULT NOW(),
    #         ended_at TIMESTAMP,
    #         index INTEGER NOT NULL,
    #         status TEXT NOT NULL,
    #         message TEXT,
    #         metadata JSONB DEFAULT '{}',            
    #         branch_id INTEGER NOT NULL,
    #         FOREIGN KEY (branch_id) REFERENCES branches(id)
    #     );
                
    #     CREATE INDEX IF NOT EXISTS idx_turns_branch_id ON turns (branch_id);
    #     CREATE INDEX IF NOT EXISTS idx_turns_index ON turns (index DESC);
    #     """)
        
    #     # partition_id INTEGER NOT NULL REFERENCES "{partition_table}" ({key}) ON DELETE CASCADE,
        
    #     # await cls.create_branch(name="main")
    # @classmethod
    # async def add_partition_id_to_turns(cls, partition_table: str, key: str):
    #     """Add a partition_id column to the table"""
    #     await PGConnectionManager.execute(f"""
    #     ALTER TABLE turns ADD COLUMN IF NOT EXISTS partition_id INTEGER NOT NULL REFERENCES "{partition_table}" ({key}) ON DELETE CASCADE;
    #     CREATE INDEX IF NOT EXISTS idx_turns_partition_id ON turns (partition_id);
    #     """)

    

    @classmethod
    def create_table(cls, namespace: "PostgresNamespace") -> str:
        """Create a table for a namespace"""
        if not namespace.table_name:
            raise ValueError("Table name is not set")
        
        sql = f"""CREATE TABLE IF NOT EXISTS "{namespace.table_name}" (\n"""
        
        for field in namespace.iter_fields():
            sql += f'"{field.name}" {field.sql_type}'
            if field.is_optional or field.is_foreign_key:
                sql += " NULL"
            else:
                sql += " NOT NULL"
            
            # Add primary key if specified
            if field.is_primary_key:
                sql += " PRIMARY KEY"
            
            # Add index if specified
            # elif field.index:
            #     sql += f" {field.index}"
                
            sql += ",\n"
        
        # Add versioning fields only if the namespace is versioned
        # if hasattr(namespace, "is_versioned") and namespace.is_versioned:
        #     sql += '"branch_id" INTEGER NOT NULL REFERENCES "branches" (id),\n'
        #     sql += '"turn_id" INTEGER NOT NULL REFERENCES "turns" (id),\n'
            
        # if hasattr(namespace, "is_repo") and namespace.is_repo:
            # sql += '"main_branch_id" INTEGER NOT NULL REFERENCES "branches" (id),\n'
            
        # Remove trailing comma
        sql = sql[:-2]
        sql += "\n);"
        
        # Execute the SQL to create the table
        cls.execute(sql)
        
        # Create indices for versioning fields if the namespace is versioned
        if hasattr(namespace, "is_versioned") and namespace.is_versioned:
            cls.create_index_for_column(namespace, "branch_id")
            cls.create_index_for_column(namespace, "turn_id")
            cls.create_index_for_column(namespace, "created_at", order="DESC")
        
        return sql
    
    @classmethod
    def update_table_fields(cls, table_name: str, fields: "list[PgFieldInfo]"):
        """Update the fields of a table"""
        sql = ''
        for field in fields:
            sql += f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{field.name}" {field.sql_type}'
            if field.is_optional:
                sql += " NULL"
            else:
                sql += " NOT NULL"
            sql += ",\n"
        sql = sql[:-2]
        sql += ";   "
        cls.execute(sql)
    
    @classmethod
    def create_index_for_column(cls, namespace: "PostgresNamespace", column_name: str, index_name: str | None = None, order: Literal["ASC", "DESC", ""] | None = None) -> None:
        """Create an index for a column"""
        if index_name is None:
            index_name = f"{namespace.table_name}_{column_name}_idx"
        if not order:
            order = ""
        sql = f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{namespace.table_name}" ("{column_name}" {order});'
        cls.execute(sql)
        
        
    @classmethod
    def list_enum_types(cls) -> list[str]:
        """Get all enum types"""
        sql = """
        SELECT typname, typcategory, typnamespace::regnamespace 
        FROM pg_type 
        WHERE typcategory IN ('E')
        ORDER BY typname;
        """
        res = cls.fetch(sql)
        return [row["typname"] for row in res]

    @classmethod
    def create_enum_types(cls, namespace: "PostgresNamespace") -> None:
        """Create an enum for a namespace"""
        for field in namespace.iter_fields():
            if field.is_enum:
                print("Building enum", field.enum_name, "with values", field.get_enum_values_safe())
                enum_values = ", ".join([f"'{v}'" for v in field.get_enum_values_safe()])
                query = f"""
                    DO $$ 
                    BEGIN
                        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = '{field.enum_name}') THEN
                            CREATE TYPE {field.enum_name} AS ENUM ({enum_values});
                        END IF;
                    END $$;
                    """
                cls.execute(query)
                
    @classmethod
    def drop_enum_types(cls) -> None:
        """Drop an enum for a namespace"""
        for enum_name in cls.list_enum_types():
            cls.execute(f"DROP TYPE IF EXISTS {enum_name};")

    @classmethod
    def drop_table(cls, namespace: "PostgresNamespace") -> str:
        sql = f"DROP TABLE IF EXISTS {namespace.table_name}"
        return cls.execute(sql)
    
    
    @classmethod
    def drop_many_tables(cls, table_names: list[str]) -> None:
        sql = f"DROP TABLE IF EXISTS {', '.join(table_names)}"
        cls.execute(sql)
        
    @classmethod
    def drop_all_tables(cls, exclude: list[str] | None = None) -> None:
        if exclude is None:
            exclude = []
        tables = cls.get_tables()
        tables = [table for table in tables if table not in exclude]
        if not tables:
            return
        cls.drop_many_tables(tables)
        cls.drop_enum_types()
        # for table in tables:
        #     if table not in exclude:
        #         await cls.drop_table(table)
        
    @classmethod
    def get_tables(cls, schema: str | None = "public") -> list[str]:
        sql = "SELECT table_name FROM information_schema.tables"
        if schema:
            sql += f" WHERE table_schema='{schema}'"
        res = cls.fetch(sql)
        return [row["table_name"] for row in res]
    
    
    @classmethod
    def get_table_fields(cls, table_name: str, schema: str = 'public'):
        query = """
        SELECT *
        FROM information_schema.columns
        WHERE table_schema = $1 AND table_name = $2
        ORDER BY ordinal_position
        """
        rows = PGConnectionManager.fetch(query, schema, table_name)
        return rows
        # return [(row['column_name'], row['data_type']) for row in rows]

    @classmethod
    def create_foreign_key(
        cls,
        table_name: str,
        column_name: str,
        column_type: str,
        referenced_table: str,
        referenced_column: str = "id",
        on_delete: str = "CASCADE",
        on_update: str = "CASCADE",
    ) -> None:
        """
        Create a foreign key constraint.
        
        Args:
            table_name: The name of the table
            column_name: The name of the column
            referenced_table: The name of the referenced table
            referenced_column: The name of the referenced column
            on_delete: The action to take when the referenced row is deleted
            on_update: The action to take when the referenced row is updated
        """
        # Check if the column exists
        sql = f"""
        DO $$
        BEGIN
            -- Check if the column exists; if not, add it.
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = '{table_name}'
                AND column_name = '{column_name}'
            ) THEN
                EXECUTE 'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_type}';
            END IF;
            
            -- Check if the foreign key constraint exists; if not, add it.
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'fk_{table_name}_{column_name}'
                AND conrelid = '{table_name}'::regclass
            ) THEN
                EXECUTE '
                ALTER TABLE "{table_name}"
                ADD CONSTRAINT fk_{table_name}_{column_name}
                FOREIGN KEY ("{column_name}")
                REFERENCES "{referenced_table}"("{referenced_column}")
                ON DELETE {on_delete}
                ON UPDATE {on_update}
                ';
            END IF;
        END $$;
        """
        cls.execute(sql)




    @classmethod
    def create_extension(cls, extension_name: str) -> None:
        """Create an extension"""
        cls.execute(f"CREATE EXTENSION IF NOT EXISTS {extension_name};")

