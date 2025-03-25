import enum
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

from pydantic import BaseModel, Field


class TurnStatus(str, enum.Enum):
    """Status of a turn"""
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"


class Turn(BaseModel):
    """A turn represents a point in time in a branch"""
    id: int
    created_at: datetime
    ended_at: Optional[datetime] = None
    index: int
    status: TurnStatus
    message: Optional[str] = None
    branch_id: int
    partition_id: int
    metadata: Optional[Dict[str, Any]] = None
    
    def __init__(
        self, 
        metadata: Union[Dict[str, Any], str, None] = None,
        **kwargs
    ):
        if metadata is None:
            metadata = {}
        elif isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        super().__init__(metadata=metadata, **kwargs)


class Branch(BaseModel):
    """A branch represents a line of development"""
    id: int
    name: str
    created_at: datetime
    updated_at: datetime
    forked_from_turn_index: Optional[int] = None
    forked_from_branch_id: Optional[int] = None


# We don't need the Repo class anymore since we're using branch_id directly