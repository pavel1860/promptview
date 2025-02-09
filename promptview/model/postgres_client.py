from datetime import datetime
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Literal, TypedDict
from uuid import uuid4
import asyncpg
import os
import itertools
import json

from .fields import VectorSpaceMetrics

if TYPE_CHECKING:
    from .resource_manager import VectorSpace
from .query import QueryFilter, QueryProxy, FieldComparable, FieldOp, QueryOp, QueryProxyAny, QuerySet


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

    async def create_collection(self, collection_name: str, vector_spaces: list["VectorSpace"], indices: list[dict[str, str]] | None = None):
        """Create a table for vector storage with pgvector extension."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            # Enable pgvector extension if not enabled
            await conn.execute('CREATE EXTENSION IF NOT EXISTS vector;')

            # Create table with vector columns and metadata
            create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {collection_name} (
                id TEXT PRIMARY KEY,
                payload JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            """

            # Add vector columns for each vector space
            for vs in vector_spaces:
                if vs.vectorizer.type == "dense":
                    create_table_sql += f",\n{vs.name} vector({vs.vectorizer.size})"

            create_table_sql += ");"

            await conn.execute(create_table_sql)

            # Create indices
            if indices:
                for index in indices:
                    field = index['field']
                    # Create GiST index for vector columns
                    if field in [vs.name for vs in vector_spaces]:
                        await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {collection_name}_{field}_idx 
                        ON {collection_name} 
                        USING ivfflat ({field} vector_cosine_ops)
                        WITH (lists = 100);
                        """)
                    else:
                        # Create B-tree index for regular columns
                        await conn.execute(f"""
                        CREATE INDEX IF NOT EXISTS {collection_name}_{field}_idx 
                        ON {collection_name} 
                        USING btree ((payload->'{field}'));
                        """)

    async def upsert(self, namespace: str, vectors: dict[str, List[List[float]]], metadata: List[Dict], ids=None, batch_size=100):
        """Upsert vectors and metadata into the collection."""
        await self._ensure_connected()
        assert self.pool is not None

        if not ids:
            ids = [str(uuid4()) for _ in range(len(next(iter(vectors.values()))))]

        results = []
        async with self.pool.acquire() as conn:
            for chunk in chunks(zip(ids, *vectors.values(), metadata), batch_size=batch_size):
                # Prepare the SQL query
                columns = ['id'] + list(vectors.keys()) + ['payload']
                placeholders = []
                values = []
                for i, item in enumerate(chunk):
                    id_, *vecs, meta = item
                    placeholders.append(f"(${i*len(columns) + 1}, {', '.join(f'${i*len(columns) + j + 2}::vector' for j in range(len(vecs)))}, ${i*len(columns) + len(vecs) + 2}::jsonb)")
                    values.extend([id_, *[vec for vec in vecs], json.dumps(meta)])

                query = f"""
                INSERT INTO {namespace} ({', '.join(columns)})
                VALUES {', '.join(placeholders)}
                ON CONFLICT (id) DO UPDATE SET
                {', '.join(f"{col} = EXCLUDED.{col}" for col in columns[1:])}
                RETURNING *;
                """

                results.extend(await conn.fetch(query, *values))

        return results

    async def search(self, collection_name: str, query, limit=3, filters=None, with_vectors=False, threshold=None):
        """Search for similar vectors using cosine similarity."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            where_clause = ""
            if filters:
                where_clause = f"WHERE {self._build_where_clause(filters)}"

            # Assuming query contains vector name and values
            vector_name, vector_values = next(iter(query.items()))
            
            select_clause = "id, payload"
            if with_vectors:
                select_clause += f", {vector_name}"

            query = f"""
            SELECT {select_clause},
                   1 - ({vector_name} <=> $1::vector) as score
            FROM {collection_name}
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
            field = f"payload->'{query_filter.field.name}'"
            if query_filter._operator == FieldOp.NULL:
                return f"{field} IS NULL"
            elif query_filter._operator == FieldOp.EQ:
                return f"{field} = '{json.dumps(query_filter.value)}'"
            elif query_filter._operator == FieldOp.NE:
                return f"{field} != '{json.dumps(query_filter.value)}'"
            elif query_filter._operator == FieldOp.IN:
                values = [json.dumps(v) for v in query_filter.value]
                return f"{field} = ANY(ARRAY[{', '.join(values)}])"
            elif query_filter._operator == FieldOp.NOTIN:
                values = [json.dumps(v) for v in query_filter.value]
                return f"{field} != ALL(ARRAY[{', '.join(values)}])"
            elif query_filter._operator == FieldOp.RANGE:
                conditions = []
                if query_filter.value.gt is not None:
                    conditions.append(f"{field} > '{json.dumps(query_filter.value.gt)}'")
                if query_filter.value.ge is not None:
                    conditions.append(f"{field} >= '{json.dumps(query_filter.value.ge)}'")
                if query_filter.value.lt is not None:
                    conditions.append(f"{field} < '{json.dumps(query_filter.value.lt)}'")
                if query_filter.value.le is not None:
                    conditions.append(f"{field} <= '{json.dumps(query_filter.value.le)}'")
                return f"({' AND '.join(conditions)})"
        return ""

    async def delete(self, collection_name: str, ids: List[str] | List[int] | None = None, filters: Any | None = None):
        """Delete records from the collection."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            if ids:
                return await conn.execute(
                    f"DELETE FROM {collection_name} WHERE id = ANY($1::text[])",
                    ids
                )
            elif filters:
                where_clause = self._build_where_clause(filters)
                return await conn.execute(
                    f"DELETE FROM {collection_name} WHERE {where_clause}"
                )
            else:
                raise ValueError("Either ids or filters must be provided.")

    async def scroll(self, collection_name: str, filters=None, limit=10, offset=0, with_vectors=False, order_by=None):
        """Implement scrolling pagination."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            where_clause = ""
            if filters:
                where_clause = f"WHERE {self._build_where_clause(filters)}"

            order_clause = "ORDER BY id"
            if order_by:
                if isinstance(order_by, str):
                    order_clause = f"ORDER BY payload->'{order_by}'"
                elif isinstance(order_by, dict):
                    order_clause = f"ORDER BY payload->'{order_by['key']}' {order_by['direction']}"

            select_clause = "id, payload"
            if with_vectors:
                # Get all vector columns
                vector_columns = await conn.fetch("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = $1 
                    AND data_type = 'vector'
                """, collection_name)
                select_clause += ", " + ", ".join(col['column_name'] for col in vector_columns)

            query = f"""
            SELECT {select_clause}
            FROM {collection_name}
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

        async with self.pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {collection_name}")

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
            return [table['table_name'] for table in tables]

    async def get_collection(self, collection_name: str, raise_error=True):
        """Get collection (table) information."""
        await self._ensure_connected()
        assert self.pool is not None

        async with self.pool.acquire() as conn:
            try:
                info = await conn.fetchrow("""
                    SELECT * 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                """, collection_name)
                if not info and raise_error:
                    raise ValueError(f"Collection {collection_name} does not exist")
                return info
            except Exception as e:
                if raise_error:
                    raise e
                return None 