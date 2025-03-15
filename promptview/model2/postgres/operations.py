from typing import Any, Dict, List, Optional, TYPE_CHECKING
import json
import datetime as dt
from pydantic import BaseModel

from promptview.utils.db_connections import PGConnectionManager

if TYPE_CHECKING:
    from promptview.model2.postgres.namespace import PostgresNamespace


class PostgresOperations:
    """Operations for PostgreSQL database"""

    @classmethod
    async def save(cls, namespace: "PostgresNamespace", data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Save data to the database.
        
        Args:
            namespace: The namespace to save to
            data: The data to save
            
        Returns:
            The saved data with any additional fields (e.g., ID)
        """
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
        result = await PGConnectionManager.fetch_one(sql, *values)
        
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
    async def query(cls, namespace: "PostgresNamespace", filters: Optional[Dict[str, Any]] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Query records.
        
        Args:
            namespace: The namespace to query
            filters: Filters to apply to the query
            limit: Maximum number of records to return
            
        Returns:
            A list of records matching the query
        """
        # Build SQL query
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