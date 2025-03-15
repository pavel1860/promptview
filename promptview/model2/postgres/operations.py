from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union
import json
import datetime as dt
from datetime import datetime, timezone
from pydantic import BaseModel

from promptview.utils.db_connections import PGConnectionManager
from promptview.model2.versioning import Turn, Branch, TurnStatus

if TYPE_CHECKING:
    from promptview.model2.postgres.namespace import PostgresNamespace


def print_error_sql(sql: str, values: list[Any] | None = None):
    print("SQL:\n", sql)
    if values:
        print("VALUES:\n", values)

class PostgresOperations:
    """Operations for PostgreSQL database"""
    
    @classmethod
    async def initialize_versioning(cls):
        """Initialize versioning tables"""
        await PGConnectionManager.initialize()
        
        # Create required tables
        await PGConnectionManager.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            id SERIAL PRIMARY KEY,
            name TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            forked_from_turn_index INTEGER,
            forked_from_branch_id INTEGER,
            FOREIGN KEY (forked_from_branch_id) REFERENCES branches(id)
        );

        CREATE TABLE IF NOT EXISTS turns (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            ended_at TIMESTAMP,
            index INTEGER NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            metadata JSONB DEFAULT '{}',
            branch_id INTEGER NOT NULL,
            FOREIGN KEY (branch_id) REFERENCES branches(id)
        );
        """)
    
    @classmethod
    async def create_branch(cls, name: Optional[str] = None, forked_from_turn_id: Optional[int] = None) -> Branch:
        """Create a new branch"""
        # Initialize versioning if needed
        await cls.initialize_versioning()
        
        turn = None
        if forked_from_turn_id is not None:
            turn = await cls.get_turn(forked_from_turn_id)
            turn_index = turn.index
            turn_branch_id = turn.branch_id
        else:
            turn_index = 1
            turn_branch_id = None
        
        if name is None:
            if forked_from_turn_id is None:
                name = "main"
            else:
                name = f"branch_from_{forked_from_turn_id}"
        
        # Create the branch
        query = "INSERT INTO branches (name, forked_from_turn_index, forked_from_branch_id) VALUES ($1, $2, $3) RETURNING *;"
        branch_row = await PGConnectionManager.fetch_one(query, name, turn_index, turn_branch_id)
        if branch_row is None:
            raise ValueError("Failed to create branch")
        
        # Create a turn for the branch
        new_turn = await cls.create_turn(branch_row['id'], 1 if turn is None else turn.index + 1, TurnStatus.STAGED)
        
        return Branch(**dict(branch_row), last_turn=new_turn)
    
    @classmethod
    async def create_turn(cls, branch_id: int, index: int, status: TurnStatus) -> Turn:
        """Create a new turn"""
        query = "INSERT INTO turns (branch_id, index, status) VALUES ($1, $2, $3) RETURNING *;"
        turn_row = await PGConnectionManager.fetch_one(query, branch_id, index, status.value)
        if turn_row is None:
            raise ValueError("Failed to create turn")
        
        return Turn(**dict(turn_row))
    
    @classmethod
    async def get_turn(cls, turn_id: int) -> Turn:
        """Get a turn by ID"""
        query = "SELECT * FROM turns WHERE id = $1;"
        turn_row = await PGConnectionManager.fetch_one(query, turn_id)
        if turn_row is None:
            raise ValueError(f"Turn {turn_id} not found")
        
        return Turn(**dict(turn_row))
    
    @classmethod
    async def get_branch(cls, branch_id: int) -> Branch:
        """Get a branch by ID"""
        # Get the branch
        query = "SELECT * FROM branches WHERE id = $1;"
        branch_row = await PGConnectionManager.fetch_one(query, branch_id)
        if branch_row is None:
            raise ValueError(f"Branch {branch_id} not found")
        
        # Get the last turn
        query = """
        SELECT * FROM turns
        WHERE branch_id = $1
        ORDER BY index DESC
        LIMIT 1;
        """
        turn_row = await PGConnectionManager.fetch_one(query, branch_id)
        if turn_row is None:
            # Create a new turn for the branch
            turn = await cls.create_turn(branch_id, 1, TurnStatus.STAGED)
            return Branch(**dict(branch_row), last_turn=turn)
        
        return Branch(**dict(branch_row), last_turn=Turn(**dict(turn_row)))
    
    @classmethod
    async def commit_turn(cls, branch_id: int, message: Optional[str] = None) -> int:
        """Commit the current turn and create a new one"""
        # Get the branch
        branch = await cls.get_branch(branch_id)
        
        # Get the current turn
        turn = branch.last_turn
        if turn is None:
            # Create a new turn if none exists
            turn = await cls.create_turn(branch_id, 1, TurnStatus.STAGED)
            return turn.id
        
        # Update the turn
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = """
        UPDATE turns
        SET status = $1, ended_at = $2, message = $3
        WHERE id = $4
        RETURNING branch_id, index;
        """
        result = await PGConnectionManager.fetch_one(query, TurnStatus.COMMITTED.value, now, message, turn.id)
        if result is None:
            raise ValueError(f"Turn {turn.id if turn else 'unknown'} not found")
        
        branch_id = result['branch_id']
        current_index = result['index']
        
        # Create a new turn
        new_index = current_index + 1
        new_turn = await cls.create_turn(branch_id, new_index, TurnStatus.STAGED)
        
        return new_turn.id

    @classmethod
    async def save(cls, namespace: "PostgresNamespace", data: Dict[str, Any], branch_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Save data to the database with versioning support.
        
        Args:
            namespace: The namespace to save to
            data: The data to save
            branch_id: The branch ID to save to (optional)
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
        # If branch_id is provided, get the current turn
        if branch_id is not None:
            branch = await cls.get_branch(branch_id)
            # Add branch_id to the data
            data["branch_id"] = branch_id
            
            # Add turn_id to the data if last_turn exists
            if branch.last_turn is not None:
                data["turn_id"] = branch.last_turn.id
            else:
                # Create a new turn if none exists
                turn = await cls.create_turn(branch_id, 1, TurnStatus.STAGED)
                data["turn_id"] = turn.id
        
        # Check if the data has an ID
        has_id = "id" in data and data["id"] is not None
        
        if has_id:
            # Update existing record
            return await cls._update(namespace, data)
        else:
            # Insert new record
            return await cls._insert(namespace, data)
    
    @classmethod
    async def _insert(cls, namespace: "PostgresNamespace", data: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new record"""
        # Prepare data for insertion
        keys = []
        placeholders = []
        values = []
        
        for key, value in data.items():
            if key == "id" and value is None:
                continue
                
            # Handle complex types
            if isinstance(value, dict) or isinstance(value, BaseModel):
                value = json.dumps(value)
            elif isinstance(value, dt.datetime):
                # Format datetime for PostgreSQL
                value = value.isoformat()
                
            keys.append(f'"{key}"')
            placeholders.append(f'${len(values) + 1}')
            values.append(value)
            
        # Build SQL query
        sql = f"""
        INSERT INTO "{namespace.table_name}" ({", ".join(keys)})
        VALUES ({", ".join(placeholders)})
        RETURNING *;
        """
        
        # Execute query
        try:
            result = await PGConnectionManager.fetch_one(sql, *values)
        except Exception as e:
            print_error_sql(sql, values)
            raise e
        
        # Convert result to dictionary
        return dict(result) if result else {"id": 1, **data}
    
    @classmethod
    async def _update(cls, namespace: "PostgresNamespace", data: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing record"""
        # Prepare data for update
        set_parts = []
        values = []
        
        for key, value in data.items():
            if key == "id":
                continue
            
            # Handle complex types
            if isinstance(value, dict) or isinstance(value, BaseModel):
                value = json.dumps(value)
            elif isinstance(value, dt.datetime):
                # Format datetime for PostgreSQL
                value = value.isoformat()
                
            set_parts.append(f'"{key}" = ${len(values) + 1}')
            values.append(value)
            
        # Add ID to values
        values.append(data["id"])
        
        # Build SQL query
        sql = f"""
        UPDATE "{namespace.table_name}"
        SET {", ".join(set_parts)}
        WHERE id = ${len(values)}
        RETURNING *;
        """
        
        # Execute query
        result = await PGConnectionManager.fetch_one(sql, *values)
        
        # Convert result to dictionary
        return dict(result) if result else {"id": data["id"], **data}
    
    @classmethod
    async def get(cls, namespace: "PostgresNamespace", id: Any) -> Optional[Dict[str, Any]]:
        """
        Get a record by ID.
        
        Args:
            namespace: The namespace to get from
            id: The ID of the record to get
            
        Returns:
            The record if found, None otherwise
        """
        # Build SQL query
        sql = f'SELECT * FROM "{namespace.table_name}" WHERE id = $1;'
        
        # Execute query
        result = await PGConnectionManager.fetch_one(sql, id)
        
        # Convert result to dictionary
        return dict(result) if result else None
    
    @classmethod
    async def query(cls, namespace: "PostgresNamespace", branch_id: Optional[int] = None, filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Query records with versioning support.
        
        Args:
            namespace: The namespace to query
            branch_id: The branch ID to query from (optional)
            filters: Filters to apply to the query
            limit: Maximum number of records to return
            
        Returns:
            A list of records matching the query
        """
        # If branch_id is provided, use versioning query
        if branch_id is not None:
            # Get the branch
            branch = await cls.get_branch(branch_id)
            
            # Build filter clause
            filter_clause = ""
            values = []
            if filters:
                filter_parts = []
                for key, value in filters.items():
                    filter_parts.append(f'm."{key}" = ${len(values) + 1}')
                    values.append(value)
                
                if filter_parts:
                    filter_clause = f"WHERE {' AND '.join(filter_parts)}"
            
            # Build limit clause
            limit_clause = f"LIMIT {limit}" if limit else ""
            
            # Build the recursive CTE query
            sql = f"""
            WITH RECURSIVE branch_hierarchy AS (
                SELECT
                    id,
                    name,
                    forked_from_turn_index,
                    forked_from_branch_id,
                    {branch.last_turn.index if branch.last_turn else 1} AS start_turn_index
                FROM branches
                WHERE id = {branch_id}
                
                UNION ALL
                
                SELECT
                    b.id,
                    b.name,
                    b.forked_from_turn_index,
                    b.forked_from_branch_id,
                    bh.forked_from_turn_index AS start_turn_index
                FROM branches b
                JOIN branch_hierarchy bh ON b.id = bh.forked_from_branch_id
            ),
            filtered_records AS (
                SELECT
                    m.*
                FROM branch_hierarchy bh
                JOIN turns t ON bh.id = t.branch_id
                JOIN "{namespace.table_name}" m ON t.id = m.turn_id
                WHERE t.index <= bh.start_turn_index
            )
            SELECT DISTINCT ON (id) *
            FROM filtered_records
            {filter_clause}
            ORDER BY id, turn_id DESC
            {limit_clause}
            """
            
            # Execute query
            results = await PGConnectionManager.fetch(sql, *values)
            
            # Convert results to dictionaries
            return [dict(row) for row in results]
        else:
            # Regular query without versioning
            sql = f'SELECT * FROM "{namespace.table_name}"'
            
            # Add filters
            values = []
            if filters:
                where_parts = []
                for key, value in filters.items():
                    where_parts.append(f'"{key}" = ${len(values) + 1}')
                    values.append(value)
                    
                sql += f" WHERE {' AND '.join(where_parts)}"
                
            # Add limit
            if limit:
                sql += f" LIMIT {limit}"
                
            # Execute query
            results = await PGConnectionManager.fetch(sql, *values)
            
            # Convert results to dictionaries
            return [dict(row) for row in results]
    
    
    
    
    
    async def execute_query(self, sql: str, *values: Any):
        """Execute a raw SQL query"""
        return await PGConnectionManager.fetch(sql, *values)