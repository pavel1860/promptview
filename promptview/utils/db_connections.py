import os
import asyncpg
from typing import List, Optional



class PGConnectionManager:
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def initialize(cls, url: Optional[str] = None) -> None:
        if cls._pool is None:
            url = url or os.environ.get("POSTGRES_URL", "postgresql://snack:Aa123456@localhost:5432/promptview_test")
            cls._pool = await asyncpg.create_pool(dsn=url)

    @classmethod
    async def close(cls) -> None:
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        if cls._pool is None:
            await cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        async with cls._pool.acquire() as conn:
            return await conn.execute(query, *args)

    @classmethod
    async def fetch(cls, query: str, *args) -> List[asyncpg.Record]:
        if cls._pool is None:
            await cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        async with cls._pool.acquire() as conn:
            return await conn.fetch(query, *args)
        
        
    @classmethod
    async def fetch_one(cls, query: str, *args) -> asyncpg.Record:
        if cls._pool is None:
            await cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        async with cls._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)
        
        
    @classmethod
    async def drop_tables(cls, table_names: list[str]) -> None:
        for table_name in table_names:
            await cls.execute(f"""DROP TABLE IF EXISTS "{table_name}" CASCADE""")