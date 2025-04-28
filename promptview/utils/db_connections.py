import os
import asyncio
import asyncpg
from typing import List, Optional, Any, AsyncContextManager, Callable, TypeVar, cast, AsyncGenerator, Union, Awaitable
from contextlib import asynccontextmanager

T = TypeVar('T')
R = TypeVar('R')


def print_error_sql(sql: str, values: Any | None = None, error: Exception | None = None):
    print("---------- SQL ------------:\n", sql)
    if values:
        print("---------- VALUES ----------:\n", values)
    if error:
        print("---------- ERROR ----------:\n", error)


class Transaction:
    """
    A class representing a database transaction.
    
    This class provides methods for executing queries within a transaction,
    and for committing or rolling back the transaction.
    """
    def __init__(self):
        self.connection = None
        self.transaction = None
    
    async def __aenter__(self):
        if PGConnectionManager._pool is None:
            await PGConnectionManager.initialize()
        assert PGConnectionManager._pool is not None, "Pool must be initialized"
        self.connection = await PGConnectionManager._pool.acquire()
        self.transaction = self.connection.transaction()
        await self.transaction.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.transaction:
            await self.transaction.__aexit__(exc_type, exc_val, exc_tb)
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query within the transaction."""
        return await self.connection.execute(query, *args)
    
    async def fetch(self, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows from the database within the transaction."""
        return await self.connection.fetch(query, *args)
    
    async def fetch_one(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row from the database within the transaction."""
        return await self.connection.fetchrow(query, *args)
    
    async def commit(self) -> None:
        """Commit the transaction."""
        if self.transaction:
            await self.transaction.commit()
    
    async def rollback(self) -> None:
        """Roll back the transaction."""
        if self.transaction:
            await self.transaction.rollback()


class PGConnectionManager:
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def initialize(cls, url: Optional[str] = None) -> None:
        """Initialize the connection pool."""
        if cls._pool is None:
            url = url or os.environ.get("POSTGRES_URL", "postgresql://snack:Aa123456@localhost:5432/promptview_test")
            cls._pool = await asyncpg.create_pool(dsn=url)

    @classmethod
    async def close(cls) -> None:
        """Close the connection pool."""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

    @classmethod
    def transaction(cls):
        """
        Create a new transaction.
        
        This method returns a context manager that can be used to execute
        queries within a transaction.
        
        Example:
            async with PGConnectionManager.transaction() as tx:
                await tx.execute("INSERT INTO users (name) VALUES ($1)", "John")
                await tx.execute("INSERT INTO profiles (user_id) VALUES ($1)", user_id)
                # If any of the above queries fail, the transaction will be rolled back
                # Otherwise, it will be committed automatically
        """
        # if cls._pool is None:
            # raise ValueError("Pool must be initialized")
        
        # conn = await cls._pool.acquire()        
        return Transaction()

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        try:
            """Execute a query."""
            if cls._pool is None:
                await cls.initialize()
            assert cls._pool is not None, "Pool must be initialized"
            async with cls._pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            print_error_sql(query, args, e)
            raise e

    @classmethod
    async def fetch(cls, query: str, *args) -> List[asyncpg.Record]:
        """Fetch multiple rows from the database."""
        try:
            if cls._pool is None:
                await cls.initialize()
            assert cls._pool is not None, "Pool must be initialized"
            async with cls._pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            print_error_sql(query, args, e)
            raise e
    
    @classmethod
    async def fetch_one(cls, query: str, *args) -> Optional[asyncpg.Record]:
        try:
            """Fetch a single row from the database."""
            if cls._pool is None:
                await cls.initialize()
            assert cls._pool is not None, "Pool must be initialized"
            async with cls._pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            print_error_sql(query, args, e)
            raise e
    
    @classmethod
    async def drop_tables(cls, table_names: list[str]) -> None:
        """Drop multiple tables."""
        for table_name in table_names:
            await cls.execute(f"""DROP TABLE IF EXISTS "{table_name}" CASCADE""")
    
    @classmethod
    async def run_in_transaction(cls, func: Callable[[Transaction], Any]) -> Any:
        """
        Run a function within a transaction.
        
        This method creates a transaction, calls the provided function with the
        transaction as an argument, and then commits the transaction if the
        function completes successfully, or rolls it back if an exception is raised.
        
        Args:
            func: A function that takes a Transaction object and returns a value or a coroutine
            
        Returns:
            The value returned by the function
            
        Example:
            async def create_user_with_profile(name: str) -> int:
                async def _create(tx: Transaction) -> int:
                    user_id = await tx.fetch_one(
                        "INSERT INTO users (name) VALUES ($1) RETURNING id", name
                    )
                    await tx.execute(
                        "INSERT INTO profiles (user_id) VALUES ($1)", user_id["id"]
                    )
                    return user_id["id"]
                
                return await PGConnectionManager.run_in_transaction(_create)
        """
        if cls._pool is None:
            await cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        
        async with cls._pool.acquire() as conn:
            tx = Transaction(conn)
            try:
                async with tx:
                    # Call the function with the transaction
                    if asyncio.iscoroutinefunction(func):
                        # If the function is a coroutine function, await it
                        result = await func(tx)
                    else:
                        # Otherwise, call it directly
                        result = func(tx)
                    
                    # Commit the transaction
                    await tx.commit()
                    return result
            except Exception as e:
                # Transaction will be automatically rolled back by the context manager
                raise e