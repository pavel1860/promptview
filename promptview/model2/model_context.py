








from pydantic import BaseModel
from typing import Optional, Dict, Any

class ModelContext(BaseModel):
    branch_id: Optional[int] = None
    turn_id: Optional[int] = None




