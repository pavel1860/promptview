from contextvars import ContextVar
import os
import asyncpg
import enum
from datetime import datetime, timezone
from typing import List, Optional, Type, Any, Dict, Tuple

from pydantic import BaseModel


"""
A framework for version-controlling Model instances using a git-like architecture.
Models can opt-in to versioning by setting versioned=True in their Config class.
This implementation uses asyncpg directly without SQLAlchemy.
"""


class TurnStatus(enum.Enum):
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"




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
        



def model_to_table_name(model_cls: Type[Any]) -> str:
    """Utility function to get table name from a model class."""
    return model_cls.__name__.lower()


class Turn(BaseModel):
    id: int
    branch_id: int
    index: int
    status: TurnStatus
    created_at: datetime
    ended_at: datetime | None = None
    message: str | None = None
    

class Branch(BaseModel):
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    branch_index: int
    turn_counter: int
    forked_from_turn_index: int | None = None
    forked_from_branch_id: int | None = None
    

class ArtifactQuery:
    """A simple query builder for artifact records using raw SQL."""
    def __init__(self, model_type: Type[Any]) -> None:
        self.model_type = model_type
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._turn_filter: Optional[Tuple[str, int]] = None
        self._time_filter: Optional[Tuple[str, Tuple[datetime, datetime]]] = None
        # _field_filter not implemented in this simple version

    def limit(self, limit: int) -> 'ArtifactQuery':
        if limit <= 0:
            raise ValueError("Limit must be positive")
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'ArtifactQuery':
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        self._offset = offset
        return self

    def at_turn(self, turn_id: int) -> 'ArtifactQuery':
        self._turn_filter = ("at", turn_id)
        return self

    def up_to_turn(self, turn_id: int) -> 'ArtifactQuery':
        self._turn_filter = ("up_to", turn_id)
        return self

    def at_time(self, timestamp: datetime) -> 'ArtifactQuery':
        # For simplicity, we treat at_time similar to 'up_to_turn' using turn creation time
        self._time_filter = ("at", (timestamp, timestamp))
        return self

    def between(self, start_time: datetime, end_time: datetime) -> 'ArtifactQuery':
        self._time_filter = ("between", (start_time, end_time))
        return self

    async def execute(self) -> List[asyncpg.Record]:
        table_name = f"{model_to_table_name(self.model_type)}_artifacts"
        # Build the base query joining the artifact table and base_artifacts
        query = f"SELECT ba.* FROM {table_name} art JOIN base_artifacts ba ON art.id = ba.id "
        where_clauses = []

        if self._turn_filter:
            typ, turn_id = self._turn_filter
            if typ == "at":
                where_clauses.append(f"ba.turn_id = {turn_id}")
            elif typ == "up_to":
                where_clauses.append(f"ba.turn_id <= {turn_id}")

        if self._time_filter:
            # This requires joining turns to filter on created_at.
            query += "JOIN turns t ON ba.turn_id = t.id "
            typ, times = self._time_filter
            if typ == "at":
                timestamp = times[0].isoformat()
                where_clauses.append(f"t.created_at <= '{timestamp}'")
            elif typ == "between":
                start_time, end_time = times
                where_clauses.append(f"t.created_at BETWEEN '{start_time.isoformat()}' AND '{end_time.isoformat()}'")

        if where_clauses:
            query += "WHERE " + " AND ".join(where_clauses) + " "

        if self._limit is not None:
            query += f"LIMIT {self._limit} "
        if self._offset is not None:
            query += f"OFFSET {self._offset}"

        return await PGConnectionManager.fetch(query)

    async def first(self) -> Optional[asyncpg.Record]:
        self._limit = 1
        results = await self.execute()
        return results[0] if results else None

    async def last(self, n: Optional[int] = None) -> List[asyncpg.Record]:
        if n is not None:
            self._limit = n
        # Implementation for last is not detailed; returning empty list for now
        return []



ARTIFCAT_LOG_CTX = ContextVar("ARTIFCAT_LOG_CTX", default=None)

class ArtifactLog:
    """
    Main class for managing versioned models and their artifacts using asyncpg.
    """
    def __init__(self, head_id: Optional[int] = None) -> None:        
        self._artifact_tables: Dict[str, str] = {}
        self._head: Optional[Dict[str, Any]] = None
        self._token = None
        self._head_id = head_id
        
    @classmethod
    def get_current(cls) -> "ArtifactLog":
        artifact_log = ARTIFCAT_LOG_CTX.get()
        if artifact_log is None:
            raise ValueError("No artifact log found")
        return artifact_log
    
    async def __aenter__(self):
        await self.init_head(self._head_id)
        self._token = ARTIFCAT_LOG_CTX.set(self)
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        ARTIFCAT_LOG_CTX.reset(self._token)
        
    @property
    def is_initialized(self) -> bool:
        return self._head is not None

    async def initialize_tables(self) -> None:
        # Initialize the asyncpg pool if not already done
        await PGConnectionManager.initialize()
        # Create required extensions and tables
        await PGConnectionManager.execute("CREATE EXTENSION IF NOT EXISTS ltree;")

        await PGConnectionManager.execute("""
            CREATE TABLE IF NOT EXISTS branches (
                id SERIAL PRIMARY KEY,
                name TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                branch_index INTEGER NOT NULL,
                turn_counter INTEGER NOT NULL,
                forked_from_turn_index INTEGER,
                forked_from_branch_id INTEGER,
                FOREIGN KEY (forked_from_branch_id) REFERENCES branches(id)
            );
        """)

        await PGConnectionManager.execute("""
            CREATE TABLE IF NOT EXISTS turns (
                id SERIAL PRIMARY KEY,
                branch_id INTEGER NOT NULL,
                index INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                ended_at TIMESTAMP,
                message TEXT,
                FOREIGN KEY (branch_id) REFERENCES branches(id),
                local_state JSONB
            );
        """)

        await PGConnectionManager.execute("""
            CREATE TABLE IF NOT EXISTS heads (
                id SERIAL PRIMARY KEY,
                branch_id INTEGER NOT NULL,
                turn_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (branch_id) REFERENCES branches(id),
                FOREIGN KEY (turn_id) REFERENCES turns(id)
            );
        """)

        await PGConnectionManager.execute("""
            CREATE TABLE IF NOT EXISTS base_artifacts (
                id SERIAL PRIMARY KEY,
                type TEXT,
                model_id TEXT,
                turn_id INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                FOREIGN KEY (turn_id) REFERENCES turns(id)
            );
        """)

    async def drop_tables(self) -> None:
        # Drop all main tables and dynamic artifact tables
        await PGConnectionManager.execute("DROP TABLE IF EXISTS heads CASCADE;")
        await PGConnectionManager.execute("DROP TABLE IF EXISTS turns CASCADE;")
        await PGConnectionManager.execute("DROP TABLE IF EXISTS branches CASCADE;")
        await PGConnectionManager.execute("DROP TABLE IF EXISTS base_artifacts CASCADE;")
        for table in self._artifact_tables.values():
            await PGConnectionManager.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
        self._artifact_tables = {}

    async def register_model(self, model_cls: Type[Any]) -> str:
        """
        Register a versioned model and create its artifact table.
        """
        table_name = f"{model_to_table_name(model_cls)}_artifacts"
        if table_name in self._artifact_tables:
            return self._artifact_tables[table_name]

        query = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id INTEGER PRIMARY KEY,
                FOREIGN KEY (id) REFERENCES base_artifacts(id) ON DELETE CASCADE
            );
        """
        await PGConnectionManager.execute(query)
        self._artifact_tables[table_name] = table_name
        return table_name

    async def init_head(self, head_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Initialize a new head with a main branch and initial turn.
        If head_id is provided, load the existing head.
        """
        if head_id is not None:
            query = "SELECT * FROM heads WHERE id = $1;"
            rows = await PGConnectionManager.fetch(query, head_id)
            if rows:
                self._head = dict(rows[0])
                return self._head

        # Create main branch
        query = "INSERT INTO branches (name, branch_index, turn_counter, forked_from_turn_index, forked_from_branch_id) VALUES ($1, $2, $3, $4, $5) RETURNING id;"
        branch_rows = await PGConnectionManager.fetch(query, "main", 0, 0, None, None)
        branch_id = branch_rows[0]['id']

        # Create initial turn
        query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING id;"
        turn_rows = await PGConnectionManager.fetch(query, branch_id, 1, TurnStatus.STAGED.value)
        turn_id = turn_rows[0]['id']

        # Create head
        query = "INSERT INTO heads (branch_id, turn_id) VALUES ($1, $2) RETURNING id;"
        head_rows = await PGConnectionManager.fetch(query, branch_id, turn_id)
        new_head_id = head_rows[0]['id']
        self._head = {"id": new_head_id, "branch_id": branch_id, "turn_id": turn_id}
        return self._head

    @property
    def head(self) -> Dict[str, Any]:
        if self._head is None:
            raise ValueError("No active head found")
        return self._head
    
    
    def get_upsert_values(self, model_type: Type[Any]):
        """
        type, turn_id
        """

    # async def stage_artifact(self, model_instance: Any) -> int:
    #     """
    #     Stage a model instance as an artifact in the current turn.
    #     The model must have a Config with versioned=True and an 'id' attribute.
    #     """
    #     config = getattr(model_instance.__class__, 'Config', None)
    #     if not config or not getattr(config, 'versioned', False):
    #         raise ValueError(f"Model {model_instance.__class__.__name__} is not versioned")

    #     artifact_table = await self.register_model(model_instance.__class__)
    #     current_head = self.head
    #     if not current_head:
    #         raise ValueError("No active head found")

    #     # Insert into base_artifacts table
    #     query = "INSERT INTO base_artifacts (type, model_id, turn_id) VALUES ($1, $2, $3) RETURNING id;"
    #     artifact_type = artifact_table  # using table name as identifier
    #     rows = await PGConnectionManager.fetch(query, artifact_type, model_instance.id, current_head['turn_id'])
    #     artifact_id = rows[0]['id']

    #     # Insert into the artifact-specific table
    #     query = f"INSERT INTO {artifact_table} (id) VALUES ($1) RETURNING id;"
    #     await PGConnectionManager.fetch(query, artifact_id)

    #     return artifact_id

    async def commit_turn(self, message: Optional[str] = None) -> int:
        """
        Commit the current turn and create a new one.
        """
        if self._head is None:
            raise ValueError("No active head found")

        head = self._head
        # Convert aware datetime to naive by removing tzinfo
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = "UPDATE turns SET status = $1, ended_at = $2, message = $3 WHERE id = $4 RETURNING branch_id, index;"
        rows = await PGConnectionManager.fetch(query, TurnStatus.COMMITTED.value, now, message, head['turn_id'])
        branch_id = rows[0]['branch_id']
        current_index = rows[0]['index']

        new_index = current_index + 1
        query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING id;"
        new_turn_rows = await PGConnectionManager.fetch(query, branch_id, new_index, TurnStatus.STAGED.value)
        new_turn_id = new_turn_rows[0]['id']

        query = "UPDATE heads SET turn_id = $1 WHERE id = $2;"
        await PGConnectionManager.execute(query, new_turn_id, head['id'])
        head['turn_id'] = new_turn_id
        return new_turn_id

    async def branch_from(self, turn_id: int, name: Optional[str] = None, check_out: bool = False) -> int:
        """
        Create a new branch from a specific turn.
        """
        query = "SELECT * FROM turns WHERE id = $1;"
        rows = await PGConnectionManager.fetch(query, turn_id)
        if not rows:
            raise ValueError(f"Turn {turn_id} not found")
        source_turn = dict(rows[0])

        current_head = self.head
        if not current_head:
            raise ValueError("No active head found")

        new_branch_name = name if name is not None else f"branch_from_{turn_id}"
        # query = "SELECT path FROM branches WHERE id = $1;"
        # branch_rows = await PGConnectionManager.fetch(query, source_turn['branch_id'])
        # branch_path = branch_rows[0]['path']
        # new_path = branch_path + '.' + str(turn_id)

        query = "INSERT INTO branches (name, branch_index, turn_counter, forked_from_turn_index, forked_from_branch_id) VALUES ($1, $2, $3, $4, $5) RETURNING id;"
        new_branch_rows = await PGConnectionManager.fetch(query, new_branch_name, 0,0, source_turn['index'], source_turn['branch_id'])
        new_branch_id = new_branch_rows[0]['id']

        if check_out:
            await self.checkout_branch(new_branch_id)
            # query = "UPDATE heads SET branch_id = $1, turn_id = $2 WHERE id = $3;"
            # await PGConnectionManager.execute(query, new_branch_id, turn_id, current_head['id'])
            # current_head['branch_id'] = new_branch_id
            # current_head['turn_id'] = turn_id

        return new_branch_id

    async def checkout_branch(self, branch_id: int) -> None:
        """
        Switch HEAD to a different branch.
        """
        query = "SELECT * FROM branches WHERE id = $1;"
        rows = await PGConnectionManager.fetch(query, branch_id)
        if not rows:
            raise ValueError(f"Branch {branch_id} not found")

        current_head = self.head
        if not current_head:
            raise ValueError("No active head found")

        query = "SELECT * FROM turns WHERE branch_id = $1 AND status = $2 ORDER BY index DESC LIMIT 1;"
        turn_rows = await PGConnectionManager.fetch(query, branch_id, TurnStatus.STAGED.value)
        if turn_rows:
            turn_id = turn_rows[0]['id']
        else:
            query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING id;"
            turn_row = await PGConnectionManager.fetch(query, branch_id, 1, TurnStatus.STAGED.value)
            turn_id = turn_row[0]['id']

        query = "UPDATE heads SET branch_id = $1, turn_id = $2 WHERE id = $3;"
        await PGConnectionManager.execute(query, branch_id, turn_id, current_head['id'])
        current_head['branch_id'] = branch_id
        current_head['turn_id'] = turn_id

    async def revert_turn(self) -> int:
        """
        Revert the current turn and create a new one.
        """
        current_head = self.head
        if not current_head:
            raise ValueError("No active head found")

        now = datetime.utcnow()
        query = "UPDATE turns SET status = $1, ended_at = $2 WHERE id = $3;"
        await PGConnectionManager.execute(query, TurnStatus.REVERTED.value, now, current_head['turn_id'])

        query = "SELECT branch_id, index FROM turns WHERE id = $1;"
        row = await PGConnectionManager.fetch(query, current_head['turn_id'])
        branch_id = row[0]['branch_id']
        new_index = row[0]['index'] + 1

        query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING id;"
        new_turn_row = await PGConnectionManager.fetch(query, branch_id, new_index, TurnStatus.STAGED.value)
        new_turn_id = new_turn_row[0]['id']

        query = "UPDATE heads SET turn_id = $1 WHERE id = $2;"
        await PGConnectionManager.execute(query, new_turn_id, current_head['id'])
        current_head['turn_id'] = new_turn_id
        return new_turn_id

    async def revert_to_turn(self, turn_id: int) -> int:
        """
        Revert to a specific turn, marking all later turns as reverted and creating a new turn.
        """
        query = "SELECT * FROM turns WHERE id = $1;"
        rows = await PGConnectionManager.fetch(query, turn_id)
        if not rows:
            raise ValueError(f"Turn {turn_id} not found")
        target_turn = dict(rows[0])

        current_head = self.head
        if not current_head:
            raise ValueError("No active head found")

        query = "UPDATE turns SET status = $1, ended_at = $2 WHERE branch_id = $3 AND index > $4 AND status != $5;"
        now = datetime.utcnow()
        await PGConnectionManager.execute(query, TurnStatus.REVERTED.value, now, target_turn['branch_id'], target_turn['index'], TurnStatus.REVERTED.value)

        new_index = target_turn['index'] + 1
        query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING id;"
        new_turn_row = await PGConnectionManager.fetch(query, target_turn['branch_id'], new_index, TurnStatus.STAGED.value)
        new_turn_id = new_turn_row[0]['id']

        query = "UPDATE heads SET branch_id = $1, turn_id = $2 WHERE id = $3;"
        await PGConnectionManager.execute(query, target_turn['branch_id'], new_turn_id, current_head['id'])
        current_head['branch_id'] = target_turn['branch_id']
        current_head['turn_id'] = new_turn_id
        return new_turn_id

    def get_artifact(self, model_type: Type[Any]) -> ArtifactQuery:
        """
        Get a query builder for artifacts of a given model.
        """
        return ArtifactQuery(model_type)

    async def get_turn(self, turn_id: int) -> Turn:
        query = "SELECT * FROM turns WHERE id = $1;"
        rows = await PGConnectionManager.fetch(query, turn_id)
        if not rows:
            raise ValueError(f"Turn {turn_id} not found")
        return Turn(**dict(rows[0]))

    async def get_branch(self, branch_id: int) -> Dict[str, Any]:
        query = "SELECT * FROM branches WHERE id = $1;"
        rows = await PGConnectionManager.fetch(query, branch_id)
        if not rows:
            raise ValueError(f"Branch {branch_id} not found")
        return dict(rows[0])
    
    
    async def get_artifact_list(self, artifact_table: str, limit: int = 10, offset: int = 0, order_by: str = "created_at", order_direction: str = "DESC") -> List[dict]:
        
        turn = await self.get_turn(self.head["turn_id"])
        query = self._artifact_cte_query(
            turn,
            artifact_table=artifact_table,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            offset=offset
        )
        rows = await PGConnectionManager.fetch(query)        
        return [dict(row) for row in rows]
    
    async def get_turn_list(self, limit: int = 10, status: Optional[TurnStatus] = None, offset: int = 0, order_by: str = "created_at", order_direction: str = "DESC") -> List[Turn]:
        turn = await self.get_turn(self.head["turn_id"])
        query = self._turn_cte_query(
            turn,
            order_by=f"t.{order_by}",
            order_direction=order_direction,
            limit=limit,
            offset=offset,
            filter_query=f"t.status = '{status.value}'" if status else ""
        )
        rows = await PGConnectionManager.fetch(query)        
        return [Turn(**dict(row)) for row in rows]
    
    async def get_branch_list(self, limit: int = 10, offset: int = 0, order_by: str = "created_at", order_direction: str = "DESC") -> List[Branch]:
        turn = await self.get_turn(self.head["turn_id"])
        query = self._branch_cte_query(turn, select_query=f"SELECT * FROM branch_hierarchy ORDER BY {order_by} {order_direction} LIMIT {limit} OFFSET {offset}", minimal_fields=False)
        rows = await PGConnectionManager.fetch(query)
        return [Branch(**dict(row)) for row in rows]
    
    async def execute_query(self, query: str) -> List[dict]:
        rows = await PGConnectionManager.fetch(query)        
        return [dict(row) for row in rows]
    
    def _branch_cte_query(self, turn: Turn, select_query: str="SELECT * FROM branch_hierarchy", minimal_fields: bool=True) -> str:
        if minimal_fields:
            fields_base = """
                id,
                name,
                forked_from_turn_index,
                forked_from_branch_id,
            """
            fields_step = """
                b.id,
                b.name,
                b.forked_from_turn_index,
                b.forked_from_branch_id,
            """
        else:
            fields_base = """
                *,
            """
            fields_step = """
                b.*,
            """
                
        query = f"""
        WITH RECURSIVE branch_hierarchy AS (
            SELECT 
                {fields_base}
                {turn.index} as start_turn_index
            FROM branches
            WHERE id={turn.branch_id}

            UNION ALL

            SELECT
                {fields_step}
                bh.forked_from_turn_index as start_turn_index
            FROM branches b
            JOIN branch_hierarchy bh ON b.id=bh.forked_from_branch_id
        )
        {select_query}     
        """
        return query
    
    def _turn_cte_query(
        self, 
        turn: Turn,
        select_query: str="t.*",
        filter_query: str="", 
        join_query: str="", 
        order_by: str="t.created_at", 
        order_direction: str="DESC", 
        limit: int=10, 
        offset: int=0
    ):
        
        turn_select_query = f"""
        SELECT 
            {select_query}
        FROM branch_hierarchy bh 
        LEFT JOIN turns t ON bh.id = t.branch_id
        {join_query}
        WHERE t.index <= bh.start_turn_index
        {"AND " + filter_query if filter_query else ""}
        ORDER BY {order_by} {order_direction}
        LIMIT {limit} OFFSET {offset};
        """
        return self._branch_cte_query(turn, select_query=turn_select_query)
    
    
    def _artifact_cte_query(
        self,
        turn: Turn,
        artifact_table: str,
        filter_query: str="",
        order_by: str="m.created_at",
        order_direction: str="DESC",
        limit: int=10,
        offset: int=0
    ) -> str:
        query = self._turn_cte_query(
            turn, 
            select_query=f"m.*", 
            join_query=f"RIGHT JOIN {artifact_table} m on t.id=m.turn_id", 
            filter_query=filter_query,
            order_by=order_by,
            order_direction=order_direction,
            limit=limit,
            offset=offset
        )
        return query
    
    