
import enum
from typing import List
from promptview.model2.model import Model
from promptview.model2.fields import KeyField, ModelField, RelationField
import datetime as dt




class TurnStatus(enum.StrEnum):
    """Status of a turn"""
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"



class Turn(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    ended_at: dt.datetime | None = ModelField(default=None)
    index: int = ModelField()
    status: TurnStatus = ModelField(default=TurnStatus.STAGED)
    message: str | None = ModelField(default=None)
    branch_id: int = ModelField(foreign_key=True)
    trace_id: str | None = ModelField(default=None)
    
    
    

class Branch(Model):
    id: int = KeyField(primary_key=True)
    name: str | None = ModelField(default=None)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    forked_from_index: int | None = ModelField(default=None)
    forked_from_branch_id: int | None = ModelField(default=None)
    current_index: int = ModelField(default=0)
    turns: List[Turn] = RelationField(foreign_key="branch_id")
    children: List["Branch"] = RelationField(foreign_key="forked_from_branch_id")
    
    async def fork(self, index: int, name: str | None = None):
        branch = await Branch(
            forked_from_index=index,
            forked_from_branch_id=self.id,
            name=name,
        ).save()
        return branch
