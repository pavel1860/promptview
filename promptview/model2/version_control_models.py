
import enum
import contextvars
from typing import TYPE_CHECKING, List, TypeVar, overload

from promptview.model2.model import Model
from promptview.model2.fields import KeyField, ModelField, RelationField
import datetime as dt

from promptview.model2.postgres.fields_query import NamespaceQueryFields
if TYPE_CHECKING:
    from promptview.model2.artifact_model import ArtifactModel

CURR_TURN = contextvars.ContextVar("curr_turn")
CURR_BRANCH = contextvars.ContextVar("curr_branch")

class TurnStatus(enum.StrEnum):
    """Status of a turn"""
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"


TURN_MODEL = TypeVar("TURN_MODEL", bound="TurnModel")

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
    _auto_commit: bool = True
    
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
        if exc_type is not None:
            await self.revert()
        elif self._auto_commit:
            await self.commit()
    
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
        
    @overload  
    async def add(self, obj: TURN_MODEL, **kwargs) -> TURN_MODEL:
        ...
    
    @overload
    async def add(self, obj: "Model", **kwargs) -> "Model":
        ...
        
    async def add(self, obj: "Model", **kwargs) -> "Model":
        if not isinstance(obj, TurnModel):
            raise TypeError("Can only add ArtifactModel instances")
        obj.turn_id = self.id
        obj.branch_id = self.branch_id
        return await obj.save()



class Branch(Model):
    _namespace_name = "branches"
    id: int = KeyField(primary_key=True)
    name: str | None = ModelField(default=None)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    forked_from_index: int | None = ModelField(default=None)
    forked_from_branch_id: int | None = ModelField(default=None)
    current_index: int = ModelField(default=0)
    turns: List[Turn] = RelationField(foreign_key="branch_id")
    children: List["Branch"] = RelationField(foreign_key="forked_from_branch_id")
    
    
    async def fork(self, index: int | None = None, name: str | None = None, turn: Turn | None = None):
        if turn is not None:
            index = turn.index
        elif index is None:
            raise ValueError("Index is required")
        
        
        branch = await Branch(
            forked_from_index=index,
            forked_from_branch_id=self.id,
            name=name,
        ).save()
        return branch
    
    
    async def add_turn(self, message: str | None = None, status: TurnStatus = TurnStatus.STAGED, **kwargs):
        query = f"""
        WITH updated_branch AS (
            UPDATE branches
            SET current_index = current_index + 1
            WHERE id = $1
            RETURNING id, current_index
        ),
        new_turn AS (
            INSERT INTO turns (branch_id, index, created_at, status{"".join([", " + k for k in kwargs.keys()])})
            SELECT id, current_index, current_timestamp, $2{"".join([", $" + str(i) for i in range(3, len(kwargs) + 3)])}
            FROM updated_branch
            RETURNING *
        )
        SELECT * FROM new_turn;
        """        
        turn_ns = Turn.get_namespace()
        
        turn_record = await turn_ns.fetch(query, self.id, status.value, *[kwargs[k] for k in kwargs.keys()])
        if not turn_record:
            raise ValueError("Failed to add turn")
        return Turn(**turn_record[0])
        
        
        
        

    
    


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
    
    
    
    
    
    
    
    
    
class TurnModel(Model):
    id: int = KeyField(primary_key=True)    
    branch_id: int = ModelField(foreign_key=True)
    turn_id: int = ModelField(foreign_key=True)    
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime | None = ModelField(default=None)
    deleted_at: dt.datetime | None = ModelField(default=None)