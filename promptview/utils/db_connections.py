import os
import asyncio
import asyncpg
import traceback
import logging
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Any, AsyncContextManager, Callable, TypeVar, cast, AsyncGenerator, Union, Awaitable
from contextlib import asynccontextmanager
# import psycopg2
# from psycopg2 import pool
if TYPE_CHECKING:
    from psycopg2.pool import SimpleConnectionPool

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


def log_database_error(operation: str, sql: str = None, values: Any = None, error: Exception = None, attempt: int = None, max_attempts: int = None):
    """Structured logging for database errors"""
    timestamp = datetime.utcnow().isoformat()
    error_context = {
        'timestamp': timestamp,
        'operation': operation,
        'error_type': type(error).__name__ if error else 'Unknown',
        'error_message': str(error) if error else 'No error message',
    }
    
    if attempt is not None and max_attempts is not None:
        error_context['retry_info'] = f'attempt {attempt}/{max_attempts}'
    
    if sql:
        # Truncate long SQL for readability
        sql_preview = sql[:200] + '...' if len(sql) > 200 else sql
        error_context['sql'] = sql_preview
    
    if values:
        error_context['parameters'] = str(values)[:100]  # Limit parameter logging
    
    # Log the structured error
    logger.error(f"DATABASE_ERROR: {error_context}")
    
    # Also print the full stack trace for debugging
    if error:
        logger.error(f"Full traceback:\n{traceback.format_exc()}")
    
    # For backward compatibility, also print to stdout in structured format
    print(f"🔴 DB ERROR [{timestamp}] {operation}: {error}")
    if sql:
        print(f"📄 SQL: {sql_preview}")
    if attempt:
        print(f"🔄 Retry: {attempt}/{max_attempts}")


class Transaction:
    """
    A class representing a database transaction.
    
    This class provides methods for executing queries within a transaction,
    and for committing or rolling back the transaction.
    """
    def __init__(self):
        self.connection: Optional[asyncpg.Connection] = None
        self.transaction: Optional[Any] = None
    
    async def __aenter__(self):
        if PGConnectionManager._pool is None:
            await PGConnectionManager.initialize()
        assert PGConnectionManager._pool is not None, "Pool must be initialized"
        self.connection = await PGConnectionManager._pool.acquire()
        if self.connection is None:
            raise RuntimeError("Failed to acquire a database connection.")
        self.transaction = self.connection.transaction()
        await self.transaction.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.transaction:
            await self.transaction.__aexit__(exc_type, exc_val, exc_tb)
    
    async def execute(self, query: str, *args) -> str:
        """Execute a query within the transaction."""
        if self.connection is None:
            raise RuntimeError("Connection is not initialized.")
        return await self.connection.execute(query, *args)
    
    async def executemany(self, query: str, args_list: List[tuple]) -> None:
        """Execute a query multiple times with different parameters within the transaction."""
        if self.connection is None:
            raise RuntimeError("Connection is not initialized.")
        return await self.connection.executemany(query, args_list)
    
    async def fetch(self, query: str, *args) -> List[dict]:
        """Fetch multiple rows from the database within the transaction as list of dicts."""
        if self.connection is None:
            raise RuntimeError("Connection is not initialized.")
        rows = await self.connection.fetch(query, *args)
        return [dict(row) for row in rows]
    
    async def fetch_one(self, query: str, *args) -> Optional[dict]:
        """Fetch a single row from the database within the transaction as dict."""
        if self.connection is None:
            raise RuntimeError("Connection is not initialized.")
        row = await self.connection.fetchrow(query, *args)
        return dict(row) if row else None
    
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
    _initialization_lock = asyncio.Lock()

    @classmethod
    async def initialize(cls, url: Optional[str] = None) -> None:
        """Initialize the connection pool if not already initialized."""
        # Use a lock to prevent multiple concurrent initializations
        async with cls._initialization_lock:
            if cls._pool is None:
                url = url or os.environ.get("POSTGRES_URL", "postgresql://snack:Aa123456@localhost:5432/promptview_test")
                
                # Get pool configuration from environment variables with sensible defaults
                min_size = int(os.environ.get("POSTGRES_POOL_MIN_SIZE", "1"))
                max_size = int(os.environ.get("POSTGRES_POOL_MAX_SIZE", "5"))
                max_inactive_lifetime = float(os.environ.get("POSTGRES_MAX_INACTIVE_LIFETIME", "30.0"))
                command_timeout = float(os.environ.get("POSTGRES_COMMAND_TIMEOUT", "20.0"))
                
                # Create pool with configurable settings
                cls._pool = await asyncpg.create_pool(
                    dsn=url,
                    min_size=min_size,
                    max_size=max_size,
                    max_inactive_connection_lifetime=max_inactive_lifetime,
                    command_timeout=command_timeout,
                    server_settings={
                        'application_name': 'promptview',
                        'jit': 'off'  # Disable JIT for faster connection setup
                    }
                )
                
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
    async def get_connection(cls) -> AsyncContextManager[asyncpg.Connection]:
        """Get a connection from the pool with proper context management."""
        if cls._pool is None:
            await cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        
        # This ensures the connection is always returned to the pool
        return cls._pool.acquire()

    @classmethod
    async def execute(cls, query: str, *args) -> str:
        """Execute a query with proper connection management and retry logic."""
        max_retries = int(os.environ.get("POSTGRES_MAX_RETRIES", "3"))
        retry_delay = float(os.environ.get("POSTGRES_RETRY_DELAY", "0.5"))
        
        for attempt in range(max_retries + 1):
            try:
                if cls._pool is None:
                    await cls.initialize()
                assert cls._pool is not None, "Pool must be initialized"
                async with cls._pool.acquire() as conn:
                    return await conn.execute(query, *args)
            except (asyncpg.ConnectionDoesNotExistError, 
                    asyncpg.InterfaceError, 
                    ConnectionError) as e:
                if attempt == max_retries:
                    log_database_error('execute', query, args, e, attempt + 1, max_retries + 1)
                    raise e
                log_database_error('execute_retry', query, args, e, attempt + 1, max_retries + 1)
                print(f"🔄 Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(retry_delay)
                # Reset pool on connection errors to force reconnection
                if cls._pool:
                    logger.info("🔄 Resetting connection pool due to connection error")
                    await cls._pool.close()
                    cls._pool = None
            except Exception as e:
                log_database_error('execute', query, args, e)
                raise e
    
    @classmethod
    async def executemany(cls, query: str, args_list: List[tuple]) -> None:
        """Execute a query multiple times with different parameters."""
        try:
            if cls._pool is None:
                await cls.initialize()
            assert cls._pool is not None, "Pool must be initialized"
            async with cls._pool.acquire() as conn:
                return await conn.executemany(query, args_list)
        except Exception as e:
            log_database_error('executemany', query, args_list, e)
            raise e

    @classmethod
    async def fetch(cls, query: str, *args) -> List[dict]:
        """Fetch multiple rows from the database as list of dicts."""
        max_retries = int(os.environ.get("POSTGRES_MAX_RETRIES", "3"))
        retry_delay = float(os.environ.get("POSTGRES_RETRY_DELAY", "0.5"))
        
        for attempt in range(max_retries + 1):
            try:
                if cls._pool is None:
                    await cls.initialize()
                assert cls._pool is not None, "Pool must be initialized"
                async with cls._pool.acquire() as conn:
                    rows = await conn.fetch(query, *args)
                    return [dict(row) for row in rows]
            except (asyncpg.ConnectionDoesNotExistError, 
                    asyncpg.InterfaceError, 
                    ConnectionError) as e:
                if attempt == max_retries:
                    log_database_error('fetch', query, args, e, attempt + 1, max_retries + 1)
                    raise e
                log_database_error('fetch_retry', query, args, e, attempt + 1, max_retries + 1)
                print(f"🔄 Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(retry_delay)
                # Reset pool on connection errors to force reconnection
                if cls._pool:
                    logger.info("🔄 Resetting connection pool due to connection error")
                    await cls._pool.close()
                    cls._pool = None
            except Exception as e:
                log_database_error('fetch', query, args, e)
                raise e
    
    @classmethod
    async def fetch_one(cls, query: str, *args) -> Optional[dict]:
        """Fetch a single row from the database as dict."""
        max_retries = int(os.environ.get("POSTGRES_MAX_RETRIES", "3"))
        retry_delay = float(os.environ.get("POSTGRES_RETRY_DELAY", "0.5"))
        
        for attempt in range(max_retries + 1):
            try:
                if cls._pool is None:
                    await cls.initialize()
                assert cls._pool is not None, "Pool must be initialized"
                async with cls._pool.acquire() as conn:
                    row = await conn.fetchrow(query, *args)
                    return dict(row) if row else None
            except (asyncpg.ConnectionDoesNotExistError, 
                    asyncpg.InterfaceError, 
                    ConnectionError) as e:
                if attempt == max_retries:
                    log_database_error('fetch_one', query, args, e, attempt + 1, max_retries + 1)
                    raise e
                log_database_error('fetch_one_retry', query, args, e, attempt + 1, max_retries + 1)
                print(f"🔄 Retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(retry_delay)
                # Reset pool on connection errors to force reconnection
                if cls._pool:
                    logger.info("🔄 Resetting connection pool due to connection error")
                    await cls._pool.close()
                    cls._pool = None
            except Exception as e:
                log_database_error('fetch_one', query, args, e)
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
            
            
    @classmethod
    async def create_database(cls, database_name: str, user: str, password: str, host: str = "localhost", port: int = 5432) -> None:
        """Create a new database."""
        await cls.execute(f"""CREATE DATABASE "{database_name}" WITH OWNER "{user}" ENCODING "UTF8" TEMPLATE template1""")
        
    @classmethod
    async def close(cls) -> None:
        """Close the connection pool and release all connections."""
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
        

class SyncPGConnectionManager:
    _pool: "SimpleConnectionPool | None" = None

    @classmethod
    def initialize(cls, url: Optional[str] = None) -> None:
        """Initialize the connection pool if not already initialized."""
        import psycopg2
        from psycopg2 import pool
        if cls._pool is None:
            url = url or os.environ.get("POSTGRES_URL", "postgresql://snack:Aa123456@localhost:5432/promptview_test")
            cls._pool = pool.SimpleConnectionPool(
                minconn=5,
                maxconn=20,
                dsn=url
            )

    @classmethod
    def get_connection(cls):
        """Get a connection from the pool."""
        if cls._pool is None:
            cls.initialize()
        assert cls._pool is not None, "Pool must be initialized"
        return cls._pool.getconn()

    @classmethod
    def put_connection(cls, conn) -> None:
        """Return a connection to the pool."""
        if cls._pool is not None:
            cls._pool.putconn(conn)

    @classmethod
    def close_all(cls) -> None:
        """Close all connections in the pool."""
        if cls._pool is not None:
            cls._pool.closeall()

    @classmethod
    def execute(cls, query: str, *args) -> None:
        """Execute a query with proper connection management."""
        conn = None
        try:
            conn = cls.get_connection()
            with conn.cursor() as cur:
                cur.execute(query, args)
                conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            print_error_sql(query, args, e)
            raise e
        finally:
            if conn:
                cls.put_connection(conn)

    @classmethod
    def fetch(cls, query: str, *args) -> List[dict]:
        """Fetch multiple rows from the database as list of dicts."""
        conn = None
        try:
            conn = cls.get_connection()
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, args)
                return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            print_error_sql(query, args, e)
            raise e
        finally:
            if conn:
                cls.put_connection(conn)

    @classmethod
    def fetch_one(cls, query: str, *args) -> Optional[dict]:
        """Fetch a single row from the database as dict."""
        conn = None
        try:
            conn = cls.get_connection()
            import psycopg2.extras
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(query, args)
                row = cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            print_error_sql(query, args, e)
            raise e
        finally:
            if conn:
                cls.put_connection(conn)
        
        
        
        