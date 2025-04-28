
import enum
import contextvars
from typing import List
from promptview.model2.model import Model
from promptview.model2.fields import KeyField, ModelField, RelationField
import datetime as dt


CURR_TURN = contextvars.ContextVar("curr_turn")
CURR_BRANCH = contextvars.ContextVar("curr_branch")

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
    _ctx_token: contextvars.Token | None = None
    
    
    # def model_post_init(self, __context): 
        
    
    @classmethod
    async def start(cls, branch: "Branch | int | None" = None) -> "Turn":
        branch_id = 1
        if branch is None:
            branch = Branch.current(throw_error=False)
            if branch is not None:
                branch_id = branch.id
        elif isinstance(branch, int):
            branch_id = branch
        elif isinstance(branch, Branch):
            branch_id = branch.id
        else:
            raise ValueError("Invalid branch")
        turn = await cls(branch_id=branch_id).save()        
        return turn
    
    
    async def __aenter__(self):
        self._ctx_token = CURR_TURN.set(self)
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if self._ctx_token is not None:
            CURR_TURN.reset(self._ctx_token)
    
    @classmethod
    def current(cls, throw_error: bool = True):
        try:
            turn = CURR_TURN.get()
        except LookupError:
            if throw_error:
                raise
            else:
                return None
        return turn
    
    async def commit(self):
        self.status = TurnStatus.COMMITTED
        await self.save()
    
    
    async def revert(self):
        self.status = TurnStatus.REVERTED
        await self.save()
        

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
    
    
    async def add_turn(self, index: int, status: TurnStatus):
        from promptview.model2.namespace_manager import NamespaceManager
        # ns = self.get_namespace()
        ns = NamespaceManager.get_turn_namespace()
        
        
        

    
    


    @classmethod
    def current(cls, throw_error: bool = True):
        try:
            branch = CURR_BRANCH.get()
        except LookupError:
            if throw_error:
                raise
            else:
                return None
        return branch