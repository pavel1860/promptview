from datetime import datetime, timezone
import datetime as dt
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, TypedDict, Type, get_args, get_origin
from uuid import uuid4
import asyncpg
import os
import itertools
import json
import numpy as np
from pydantic import BaseModel

from promptview.artifact_log.artifact_log3 import ArtifactLog


if TYPE_CHECKING:
    from promptview.model.model import Model

from .fields import VectorSpaceMetrics


if TYPE_CHECKING:
    from .resource_manager import VectorSpace
from .query import QueryFilter, QueryProxy, FieldComparable, FieldOp, QueryOp, QueryProxyAny, QuerySet


def unpack_list_model(pydantic_model):
    return get_args(pydantic_model)[0]

def chunks(iterable, batch_size=100):
    """A helper function to break an iterable into chunks of size batch_size."""
    it = iter(iterable)
    chunk = tuple(itertools.islice(it, batch_size))
    while chunk:
        yield chunk
        chunk = tuple(itertools.islice(it, batch_size))


class OrderBy(TypedDict):
    key: str
    direction: Literal["asc", "desc"]
    start_from: int | float | datetime


def camel_to_snake(name: str) -> str:
    """Convert CamelCase to snake_case."""
    import re
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()

def model_to_table_name(model) -> str:
    """Convert a model to a table name."""
    return camel_to_snake(model.__name__)


def stringify_vector(vector: list[float] | np.ndarray):
    if isinstance(vector, np.ndarray):
        vector = vector.tolist()
    return '[' + ', '.join(map(str, vector)) + ']'

class PostgresClient:
    def __init__(self, url=None, user=None, password=None, database=None, host=None, port=None):
        self.url = url or os.environ.get("POSTGRES_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
        if not self.url:
            self.user = user or os.environ.get("POSTGRES_USER", "postgres")
            self.password = password or os.environ.get("POSTGRES_PASSWORD", "postgres")
            self.database = database or os.environ.get("POSTGRES_DB", "postgres")
            self.host = host or os.environ.get("POSTGRES_HOST", "localhost")
            self.port = port or os.environ.get("POSTGRES_PORT", 5432)
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        """Initialize the connection pool if not already initialized."""
        if self.pool is None:
            if self.url:
                self.pool = await asyncpg.create_pool(self.url)
            else:
                self.pool = await asyncpg.create_pool(
                    user=self.user,
                    password=self.password,
                    database=self.database,
                    host=self.host,
                    port=self.port
                )

    async def close(self):
        """Close the connection pool if it exists."""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def _ensure_connected(self):
        """Ensure we have a connection pool."""
        if self.pool is None:
            await self.connect()
        assert self.pool is not None
    
    async def init_extensions(self):
        await self._ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            # Enable pgvector extension if not enabled
            return await conn.execute('''
            CREATE EXTENSION IF NOT EXISTS vector;
            CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
            ''')
            
    def build_table_sql(
        self, 
        collection_name: str, 
        model_cls: "Type[Model]", 
        vector_spaces: list["VectorSpace"], 
        indices: list[dict[str, str]] | None = None,
        versioned: bool = False,
        is_head: bool = False,
        relations: dict[str, dict[str, str]] | None = None,
    ):
        """Create a table for vector storage with pgvector extension."""

        table_name = camel_to_snake(collection_name)
        
        if versioned and is_head:
            raise ValueError("Versioned and head models cannot be created at the same time")

        
        # Get model class from the collection name to inspect fields
        
        # Create table with proper columns for each field
#         create_table_sql = f"""CREATE TABLE IF NOT EXISTS {table_name} (
# id UUID PRIMARY KEY DEFAULT uuid_generate_v4()"""
        create_table_sql = f"""CREATE TABLE IF NOT EXISTS {table_name} (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),            
            """
        if versioned:
            create_table_sql += """
            turn_id INT NOT NULL,
            FOREIGN KEY (turn_id) REFERENCES turns(id),
            branch_id INT NOT NULL,
            FOREIGN KEY (branch_id) REFERENCES branches(id),
            """
        if is_head:
            # create_table_sql += """
            # head_id INT NOT NULL,
            # FOREIGN KEY (head_id) REFERENCES heads(id),
            # """
            create_table_sql += """
            head_id INTEGER,
            FOREIGN KEY (head_id) REFERENCES heads(id),
            """
    
        # Add columns for each model field
        for field_name, field in model_cls.model_fields.items():            
            if field_name in ["id", "turn_id", "branch_id", "head_id", "_subspace", "score", "created_at", "updated_at"]:
                continue
            create_table_sql += "\n"
            field_type = field.annotation
            
            if get_origin(field_type) == list:
                field_type =unpack_list_model(field_type)
                partition = field.json_schema_extra.get("partition")
                # create_table_sql += f', FOREIGN KEY ("{field_name}") REFERENCES {model_to_table_name(field_type)} ("{partition}")'
                create_table_sql += f'"{field_name}" UUID FOREIGN KEY REFERENCES {model_to_table_name(field_type)} ("{partition}")'
            else:
                if field.json_schema_extra.get("db_type"):
                    sql_type = field.json_schema_extra.get("db_type")                
                elif field_type == bool:
                    sql_type = "BOOLEAN"
                elif field_type == int:
                    sql_type = "INTEGER"
                elif field_type == str:
                    sql_type = "TEXT"
                elif field_type == datetime or field_type == dt.datetime:
                    # TODO: sql_type = "TIMESTAMP WITH TIME ZONE"
                    sql_type = "TIMESTAMP"
                elif str(field_type).startswith("list["):
                    # Handle arrays
                    inner_type = str(field_type).split("[")[1].rstrip("]")
                    if inner_type == "int":
                        sql_type = "INTEGER[]"
                    else:
                        sql_type = "TEXT[]"
                elif str(field_type).startswith("dict") or (isinstance(field_type, type) and issubclass(field_type, BaseModel)):
                    sql_type = "JSONB"                    
                else:
                    sql_type = "TEXT"  # Default to TEXT for unknown types
            
                create_table_sql += f'"{field_name}" {sql_type},'

        # Add vector columns for each vector space
        for vs in vector_spaces:
            if vs.vectorizer.type == "dense":
                create_table_sql += f'"{vs.name}" vector({vs.vectorizer.size}),\n'
        
        relations_sql = []
            
        for relation in relations.get(table_name, []):
            # create_table_sql += f'\nFOREIGN KEY ("{relation["partition"]}") REFERENCES {relation["source_namespace"]} ("id")'
            # create_table_sql += f'\n"{relation["partition"]}" INT REFERENCES {relation["source_namespace"]}("id")'
            # relations_sql.append(f"""
            # ALTER TABLE {table_name}
            # ADD COLUMN "{relation["partition"]}" INT;
                                 
            # ALTER TABLE {table_name}
            # ADD CONSTRAINT fk_{relation["partition"]}
            # FOREIGN KEY ("{relation["partition"]}")
            # REFERENCES {relation["source_namespace"]} ("id");
            # """)
            table_name = relation["source_namespace"]
            column_name = relation["partition"]
            fk_name = f'fk_{column_name}'
            relations_sql.append(f"""
            DO $$
            BEGIN
                -- Check if the "test_case_id" column exists; if not, add it.
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                    AND table_name = '{table_name}'
                    AND column_name = '{column_name}'
                ) THEN
                    EXECUTE 'ALTER TABLE {table_name} ADD COLUMN "{column_name}" INT';
                END IF;

                -- Check if the foreign key constraint exists; if not, add it.
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = '{fk_name}'
                    AND conrelid = '{table_name}'::regclass
                ) THEN
                    EXECUTE '
                    ALTER TABLE {table_name} 
                    ADD CONSTRAINT {fk_name} 
                    FOREIGN KEY ("{column_name}") 
                    REFERENCES {table_name}("id")
                    ';
                END IF;
            END $$;

            """)
                
        create_table_sql = create_table_sql.rstrip(",")
        create_table_sql += "\n);"
        
        
        indices_sql = []

        # Create indices
        if indices:
            for index in indices:
                field = index['field']
                # Create GiST index for vector columns
                if field in [vs.name for vs in vector_spaces]:
                    indices_sql.append(f"""
                    CREATE INDEX IF NOT EXISTS {table_name}_{field}_idx 
                    ON {table_name} 
                    USING ivfflat ("{field}" vector_cosine_ops)
                    WITH (lists = 100);
                    """)
                else:
                    # Create B-tree index for regular columns
                    indices_sql.append(f"""
                    CREATE INDEX IF NOT EXISTS {table_name}_{field}_idx 
                    ON {table_name} 
                    USING btree ("{field}");
                    """)
        # return create_table_sql + "\n" + "\n".join(indices_sql)
        return create_table_sql, "\n".join(indices_sql), "\n".join(relations_sql)

    async def execute_sql(self, sql: str):
        await self._ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.execute(sql)

    async def create_collection(self, collection_name: str, model_cls: "Type[Model]", vector_spaces: list["VectorSpace"], indices: list[dict[str, str]] | None = None):
        """Create a table for vector storage with pgvector extension."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            # Enable pgvector extension if not enabled
            # Get model class from the collection name to inspect fields
            
            # Create table with proper columns for each field
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
                turn_id INT NOT NULL,
                FOREIGN KEY (turn_id) REFERENCES turns(id),
                branch_id INT NOT NULL,
                FOREIGN KEY (branch_id) REFERENCES branches(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),                
            """

            # Add columns for each model field
            for field_name, field in model_cls.model_fields.items():
                if field_name == "id" or field_name == "_subspace" or field_name == "score":  # Skip id as it's already added
                    continue
                
                field_type = field.annotation
                
                if get_origin(field_type) == list:
                    field_type =unpack_list_model(field_type)
                    partition = field.json_schema_extra.get("partition")
                    create_table_sql += f', FOREIGN KEY ("{field_name}") REFERENCES {model_to_table_name(field_type)} ("{partition}")'
                else:
                    if field_type == bool:
                        sql_type = "BOOLEAN"
                    elif field_type == int:
                        sql_type = "INTEGER"
                    elif field_type == str:
                        sql_type = "TEXT"
                    elif field_type == datetime or field_type == dt.datetime:
                        # TODO: sql_type = "TIMESTAMP WITH TIME ZONE"
                        sql_type = "TIMESTAMP"
                    elif str(field_type).startswith("list["):
                        # Handle arrays
                        inner_type = str(field_type).split("[")[1].rstrip("]")
                        if inner_type == "int":
                            sql_type = "INTEGER[]"
                        else:
                            sql_type = "TEXT[]"
                    elif str(field_type).startswith("dict") or (isinstance(field_type, type) and issubclass(field_type, BaseModel)):
                        sql_type = "JSONB"                    
                    else:
                        sql_type = "TEXT"  # Default to TEXT for unknown types
                
                    create_table_sql += f',\n"{field_name}" {sql_type}'

            # Add vector columns for each vector space
            for vs in vector_spaces:
                if vs.vectorizer.type == "dense":
                    create_table_sql += f',\n"{vs.name}" vector({vs.vectorizer.size})'

            create_table_sql += ");"

            await conn.execute(create_table_sql)

            # Create indices
            if indices:
                for index in indices:
                    field = index['field']
                    # Create GiST index for vector columns
                    if field in [vs.name for vs in vector_spaces]:
                        await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {table_name}_{field}_idx 
                        ON {table_name} 
                        USING ivfflat ("{field}" vector_cosine_ops)
                        WITH (lists = 100);
                        """)
                    else:
                        # Create B-tree index for regular columns
                        await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {table_name}_{field}_idx 
                        ON {table_name} 
                        USING btree ("{field}");
                        """)

    async def upsert(
        self,
        namespace: str,
        vectors: List[dict[str, List[float] | Any]],
        metadata: List[Dict],
        model_cls: Type[BaseModel],
        ids=None,
        batch_size=100,
        is_versioned: bool = False,
        is_head: bool = False,
        is_detached_head: bool = False
    ):
        """Upsert vectors and metadata into the collection with fixed turn_id and type fields."""
        await self._ensure_connected()
        assert self.pool is not None
        if is_versioned and is_head:
            raise ValueError("Versioned and head models cannot be created at the same time")
        artifact_values = {}
        if is_versioned:
            artifact_log = ArtifactLog.get_current()
            assert artifact_log.is_initialized
            artifact_values = {"turn_id": artifact_log.head["turn_id"], "branch_id": artifact_log.head["branch_id"]}
        if is_head:
            artifact_log = ArtifactLog()
            head = await artifact_log.create_head(init_repo=not is_detached_head)
            artifact_values = {"head_id": head["id"]}
        


        # Define the fixed values you want to add to every record.
        # You can use hard-coded values (e.g. {"turn_id": 42, "type": "my_type"})
        # or values derived from artifact_log (e.g. artifact_log.head["turn_id"])
        

        # Build the base columns from the first record and add the fixed columns.
        if vectors:
            base_columns = list(vectors[0].keys())
        else:
            base_columns = list(metadata[0].keys())

        # Remove any keys you want to skip (e.g. "_subspace") and also do not duplicate fixed keys.
        base_columns = [col for col in base_columns if col != "_subspace" and col not in artifact_values]
        # Now add the fixed columns.
        columns = base_columns + list(artifact_values.keys())

        def zip_metadata(vectors, metadata):
            if not vectors:
                for meta in metadata:
                    yield meta
            else:
                for vec, meta in zip(vectors, metadata):
                    yield {**vec, **meta}

        results = []
        async with self.pool.acquire() as conn:
            for chunk in chunks(zip_metadata(vectors, metadata), batch_size=batch_size):
                # Update each row with our fixed values.
                for item in chunk:
                    item.update(artifact_values)

                placeholders = []
                values = []
                for i, item in enumerate(chunk):
                    start_idx = i * len(columns)
                    col_placeholders = []
                    for j, col in enumerate(columns, 1):
                        placeholder_idx = start_idx + j
                        if isinstance(item[col], np.ndarray):
                            item[col] = stringify_vector(item[col])
                            col_placeholders.append(f"${placeholder_idx}::vector")
                        elif isinstance(item[col], list):
                            item[col] = stringify_vector(item[col])
                            col_placeholders.append(f"${placeholder_idx}::vector")
                        elif isinstance(item[col], dict):
                            item[col] = json.dumps(item[col])
                            col_placeholders.append(f"${placeholder_idx}::jsonb")
                        elif isinstance(item[col], BaseModel):
                            item[col] = item[col].model_dump_json()
                            col_placeholders.append(f"${placeholder_idx}::jsonb")
                        else:
                            col_placeholders.append(f"${placeholder_idx}")
                        values.append(item[col])
                    placeholders.append(f"({', '.join(col_placeholders)})")

                query = f"""
                INSERT INTO {namespace} ({', '.join(f'"{col}"' for col in columns)})
                VALUES {', '.join(placeholders)}
                RETURNING *;
                """
                results.extend(await conn.fetch(query, *values))
        
        return results

    async def search(self, collection_name: str, query, limit=3, filters=None, with_vectors=False, threshold=None):
        """Search for similar vectors using cosine similarity."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            where_clause = ""
            if filters:
                where_clause = f"WHERE {self._build_where_clause(filters)}"

            # Assuming query contains vector name and values
            vector_name, vector_values = next(iter(query.items()))
            
            select_clause = "id, payload"
            if with_vectors:
                select_clause += f', "{vector_name}"'

            query = f"""
            SELECT {select_clause},
                   1 - ("{vector_name}" <=> $1::vector) as score
            FROM {table_name}
            {where_clause}
            ORDER BY score DESC
            LIMIT {limit}
            """

            if threshold:
                query = query.replace("ORDER BY", f"HAVING score >= {threshold}\nORDER BY")

            return await conn.fetch(query, vector_values)

    def _build_where_clause(self, query_filter: QueryFilter) -> str:
        """Convert QueryFilter to SQL WHERE clause."""
        if isinstance(query_filter._operator, QueryOp):
            if query_filter._operator == QueryOp.AND:
                return f"({self._build_where_clause(query_filter._left)} AND {self._build_where_clause(query_filter._right)})"
            elif query_filter._operator == QueryOp.OR:
                return f"({self._build_where_clause(query_filter._left)} OR {self._build_where_clause(query_filter._right)})"
        elif isinstance(query_filter._operator, FieldOp):
            field = query_filter.field
            field_name = f'"{field.name}"'
            
            # Get field type information
            if hasattr(field, '_field_info'):
                field_type = field._field_info.annotation
            else:
                field_type = field.type
                
            
            # Handle JSONB fields differently
            if str(field_type).startswith("dict") or (isinstance(field_type, type) and issubclass(field_type, BaseModel)):
                json_field = f"payload->'{field.name}'"
                if query_filter._operator == FieldOp.NULL:
                    return f"{json_field} IS NULL"
                elif query_filter._operator == FieldOp.EQ:
                    return f"{json_field} = '{json.dumps(query_filter.value)}'"
                elif query_filter._operator == FieldOp.NE:
                    return f"{json_field} != '{json.dumps(query_filter.value)}'"
                elif query_filter._operator == FieldOp.IN:
                    values = [json.dumps(v) for v in query_filter.value]
                    return f"{json_field} = ANY(ARRAY[{', '.join(values)}])"
                elif query_filter._operator == FieldOp.NOTIN:
                    values = [json.dumps(v) for v in query_filter.value]
                    return f"{json_field} != ALL(ARRAY[{', '.join(values)}])"
            
            # Handle regular fields with proper type casting
            if query_filter._operator == FieldOp.NULL:
                return f"{field_name} IS NULL"
            elif query_filter._operator == FieldOp.EQ:
                if field_type == bool:
                    return f"{field_name} = {str(query_filter.value).lower()}"
                elif field_type == int:
                    return f"{field_name} = {query_filter.value}"
                elif field_type == str:
                    return f"{field_name} = '{query_filter.value}'"
                elif field_type == dt.datetime:
                    return f"{field_name} = '{query_filter.value}'"
            elif query_filter._operator == FieldOp.NE:
                if field_type == bool:
                    return f"{field_name} != {str(query_filter.value).lower()}"
                elif field_type == int:
                    return f"{field_name} != {query_filter.value}"
                elif field_type == str:
                    return f"{field_name} != '{query_filter.value}'"
                elif field_type == dt.datetime:
                    return f"{field_name} != '{query_filter.value}'"
            elif query_filter._operator == FieldOp.IN:
                if field_type == int:
                    values = [str(v) for v in query_filter.value]
                    return f"{field_name} = ANY(ARRAY[{', '.join(values)}])"
                else:
                    values = [f"'{v}'" for v in query_filter.value]
                    return f"{field_name} = ANY(ARRAY[{', '.join(values)}])"
            elif query_filter._operator == FieldOp.NOTIN:
                if field_type == int:
                    values = [str(v) for v in query_filter.value]
                    return f"{field_name} != ALL(ARRAY[{', '.join(values)}])"
                else:
                    values = [f"'{v}'" for v in query_filter.value]
                    return f"{field_name} != ALL(ARRAY[{', '.join(values)}])"
            elif query_filter._operator == FieldOp.RANGE:
                conditions = []
                if query_filter.value.gt is not None:
                    if field_type == int:
                        conditions.append(f"{field_name} > {query_filter.value.gt}")
                    else:
                        conditions.append(f"{field_name} > '{query_filter.value.gt}'")
                if query_filter.value.ge is not None:
                    if field_type == int:
                        conditions.append(f"{field_name} >= {query_filter.value.ge}")#f"{field_name} >= to_timestamp('{query_filter.value.ge.strfmt('YYYY-MM-DD HH24:MI:SS')}')"
                    # elif field_type == dt.datetime:                        
                        # conditions.append(f"{field_name} >= to_timestamp('{query_filter.value.ge.strftime('%Y-%m-%d %H:%M:%S')}')")
                    else:
                        conditions.append(f"{field_name} >= '{query_filter.value.ge}'")
                if query_filter.value.lt is not None:
                    if field_type == int:
                        conditions.append(f"{field_name} < {query_filter.value.lt}")
                    else:
                        conditions.append(f"{field_name} < '{query_filter.value.lt}'")
                if query_filter.value.le is not None:
                    if field_type == int:
                        conditions.append(f"{field_name} <= {query_filter.value.le}")
                    else:
                        conditions.append(f"{field_name} <= '{query_filter.value.le}'")
                return f"({' AND '.join(conditions)})"
        return ""

    async def delete(self, collection_name: str, ids: List[str] | List[int] | None = None, filters: Any | None = None):
        """Delete records from the collection."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            if ids:
                return await conn.execute(
                    f'DELETE FROM {table_name} WHERE id = ANY($1::text[])',
                    ids
                )
            elif filters:
                where_clause = self._build_where_clause(filters)
                return await conn.execute(
                    f"DELETE FROM {table_name} WHERE {where_clause}"
                )
            else:
                raise ValueError("Either ids or filters must be provided.")

    async def scroll(self, collection_name: str, filters=None, limit=10, offset=0, with_vectors=False, order_by=None):
        """Implement scrolling pagination."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            where_clause = ""
            if filters:
                where_clause = f"WHERE {self._build_where_clause(filters)}"

            order_clause = 'ORDER BY "id"'
            if order_by:
                if isinstance(order_by, str):
                    order_clause = f'ORDER BY "{order_by}"'
                elif isinstance(order_by, dict):
                    order_clause = f'ORDER BY "{order_by["key"]}" {order_by["direction"]}'

            select_clause = "*"
            if with_vectors:
                # Get all vector columns
                vector_columns = await conn.fetch("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = $1 
                    AND data_type = 'vector'
                """, table_name)
                if vector_columns:
                    select_clause = '"id", ' + ', '.join(f'"{r["column_name"]}"' for r in vector_columns)

            query = f"""
            SELECT {select_clause}
            FROM {table_name}
            {where_clause}
            {order_clause}
            LIMIT {limit} OFFSET {offset}
            """

            records = await conn.fetch(query)
            next_offset = offset + len(records) if len(records) == limit else None

            return records, next_offset

    async def delete_collection(self, collection_name: str):
        """Drop the collection table."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            await conn.execute(f'DROP TABLE IF EXISTS {table_name}')

    async def get_collections(self):
        """Get all collection (table) names."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            tables = await conn.fetch("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
            """)
            return [table["table_name"] for table in tables]

    async def get_collection(self, collection_name: str, raise_error=True):
        """Get collection (table) information."""
        await self._ensure_connected()
        assert self.pool is not None

        table_name = camel_to_snake(collection_name)

        async with self.pool.acquire() as conn:
            try:
                info = await conn.fetchrow("""
                    SELECT * 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                """, table_name)
                if not info and raise_error:
                    raise ValueError(f"Collection {collection_name} does not exist")
                return info
            except Exception as e:
                if raise_error:
                    raise e
                return None 

    async def execute_query(self, collection_name: str, query_set: "QuerySet", is_versioned: bool = False, is_head: bool = False):
        """Execute a query set and return the results."""
        
        table_name = collection_name
        
        if query_set.query_type == "vector":
            # Handle vector similarity search
            if not query_set._vector_query or not query_set._vector_query.vector_lookup:
                raise ValueError("Vector query not provided or vectors not embedded")
            
            vector_name, vector_values = next(iter(query_set._vector_query.vector_lookup.items()))
            vector_values = stringify_vector(vector_values)
            where_clause = ""
            if query_set._filters:
                where_clause = f"WHERE {self._build_where_clause(query_set._filters)}"

            query = f"""
            SELECT *,
                   1 - ("{vector_name}" <=> $1::vector) as score
            FROM {table_name}
            {where_clause}
            ORDER BY score DESC
            LIMIT {query_set._limit}
            """

            if query_set._vector_query.threshold:
                query = query.replace("ORDER BY", f"HAVING score >= {query_set._vector_query.threshold}\nORDER BY")

            async with self.pool.acquire() as conn:
                return await conn.fetch(query, vector_values)
                
        elif query_set.query_type == "scroll":
            # Handle regular queries with filtering and ordering
            where_clause = ""
            if query_set._filters:
                where_clause = f"WHERE {self._build_where_clause(query_set._filters)}"

            order_clause = 'ORDER BY "id"'
            if query_set._order_by:
                if isinstance(query_set._order_by, str):
                    order_clause = f'ORDER BY "{query_set._order_by}"'
                elif isinstance(query_set._order_by, dict):
                    order_clause = f'ORDER BY "{query_set._order_by["key"]}" {query_set._order_by["direction"]}'

            query = f"""
            SELECT *
            FROM {table_name}
            {where_clause}
            {order_clause}
            LIMIT {query_set._limit}
            """
            
            if query_set._offset is not None:
                query += f" OFFSET {query_set._offset}"

            if is_versioned:
                artifact_log = ArtifactLog.get_current()
                records = await artifact_log.artifact_cte_raw_query(
                    artifact_table=table_name,
                    artifact_query=query
                )
            else:
                async with self.pool.acquire() as conn:
                    records = await conn.fetch(query)
            # return res
            # async with self.pool.acquire() as conn:
            #     return await conn.fetch(query)
                
        elif query_set.query_type == "id":
            # Handle queries by ID
            if not query_set._ids:
                raise ValueError("No IDs provided for ID query")
                
            async with self.pool.acquire() as conn:
                records = await conn.fetch(
                    f'SELECT * FROM {table_name} WHERE id = ANY($1::text[])',
                    query_set._ids
                )
        else:
            raise ValueError(f"Unsupported query type: {query_set.query_type}") 
            
        return records
        
        
        
    async def retrieve(self, namespace: str, ids: List[str] | List[int]):
        await self._ensure_connected()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            return await conn.fetch(f'SELECT * FROM "{namespace}" WHERE id = ANY($1)', ids)
        