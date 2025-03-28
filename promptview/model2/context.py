
import contextvars
from enum import StrEnum
from typing import TYPE_CHECKING, Generic, Type, TypeVar

from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.versioning import ArtifactLog


    

if TYPE_CHECKING:
    from promptview.model2.model import Model, ContextModel
    from promptview.model2.versioning import Branch, Turn
    from promptview.prompt.block6 import Block, BlockList, Blockable
    
PARTITION_MODEL = TypeVar("PARTITION_MODEL", bound="Model")
CONTEXT_MODEL = TypeVar("CONTEXT_MODEL", bound="ContextModel")


CURR_CONTEXT = contextvars.ContextVar("curr_context")

class InitStrategy(StrEnum):
    START_TURN = "start_turn"    
    BRANCH_FROM = "branch_from"
    NO_PARTITION = "no_partition"
    

class Context(Generic[PARTITION_MODEL, CONTEXT_MODEL]):
    partition_model: Type[PARTITION_MODEL]
    context_model: Type[CONTEXT_MODEL]
    _partition_id: int | None
    
    _ctx_token: contextvars.Token | None
    _branch: "Branch | None"
    _turn: "Turn | None"
    
    def __init__(self, partition: "Model | int | None" = None, span_name: str | None = None):
        if isinstance(partition, int):
            self._partition_id = partition
            self._partition = None
        elif partition is None:
            ctx = Context.get_current(raise_error=True)
            if ctx is None:
                raise ValueError("Context not set")
            self._partition = ctx.partition
            self._partition_id = ctx.partition_id
        else:
            self._partition_id = partition.id
            self._partition = partition
        self._init_method = InitStrategy.NO_PARTITION
        self._init_params = {}
        self._ctx_token = None
        self._span_name = span_name
        self._branch = None
        self._turn = None
        
    @classmethod
    def get_current(cls, raise_error: bool = True):
        try:            
            ctx = CURR_CONTEXT.get()
        except LookupError:
            if raise_error:
                raise ValueError("Context not set")
            else:
                return None        
        if not isinstance(ctx, Context):
            if raise_error:
                raise ValueError("Context is not a Context")
            else:
                return None
        return ctx
    
    @classmethod
    def get_current_head(cls, turn: "int | Turn | None" = None, branch: "int | Branch | None" = None) -> tuple[int | None, int | None]: 
        ctx = Context.get_current(raise_error=False)    
        turn_id = cls.get_current_turn(turn, ctx)
        branch_id = cls.get_current_branch(branch, ctx)
        return turn_id, branch_id
    
    @classmethod
    def get_current_branch(cls, branch: "int | Branch | None" = None, ctx: "Context | None" = None):
        branch_id = 1
        if ctx is None:
            ctx = Context.get_current(raise_error=False)
        if branch:
            if isinstance(branch, int):
                branch_id = branch
            else:
                branch_id = branch.id
        else:
            if ctx:
                branch_id = ctx.branch.id
        return branch_id
    
    @classmethod
    def get_current_turn(cls, turn: "int | Turn | None" = None, ctx: "Context | None" = None):
        turn_id = None
        if ctx is None:
            ctx = Context.get_current(raise_error=False)
        if turn:
            if isinstance(turn, int):
                turn_id = turn
            elif isinstance(turn, Turn):
                turn_id = turn.id
        else:
            if ctx:
                turn_id = ctx.turn.id
        return turn_id
                
    
    @property
    def is_initialized(self):
        return self._branch is not None and self._turn is not None
    
    @property
    def partition_id(self):
        if self._partition_id is None:
            raise ValueError("Partition ID not set")
        return self._partition_id
    
    @property
    def branch(self):
        if self._branch is None:
            raise ValueError("Branch not set")
        return self._branch
    
    @property
    def turn(self):
        if self._turn is None:
            raise ValueError("Turn not set")
        return self._turn
    
    @property
    def can_push(self):
        return self._init_method != InitStrategy.NO_PARTITION
    
    @property
    def partition(self):
        if self._partition is None:
            raise ValueError("Partition not set")
        return self._partition
    
    def start_turn(self, branch_id: int = 1):
        self._init_method = InitStrategy.START_TURN
        self._init_params["branch_id"] = branch_id
        return self
    
    
    async def branch_from(self, turn_id: int, name: str | None = None):
        branch = await ArtifactLog.create_branch(forked_from_turn_id=turn_id, name=name)        
        return branch
    
    # async def branch_from(self, turn_id: int, name: str | None = None):
    #     self._init_method = InitStrategy.BRANCH_FROM
    #     self._init_params["turn_id"] = turn_id
    #     return self
    
    def build_child(self, span_name: str | None = None):
        child = Context(self.partition, span_name)
        child._branch = self._branch
        child._turn = self._turn
        return child
    
    async def _start_new_turn(self):
        if "branch_id" in self._init_params:
            branch = await NamespaceManager.get_branch(self._init_params["branch_id"])
            if branch is None:
                raise ValueError(f"Branch {self._init_params['branch_id']} not found")
            self._branch = branch
        self._turn = await NamespaceManager.create_turn(self.partition_id, self.branch.id)
        
    def _set_context(self):
        self._ctx_token = CURR_CONTEXT.set(self)
        
    def _reset_context(self):
        if self._ctx_token is not None:
            CURR_CONTEXT.reset(self._ctx_token)
        self._ctx_token = None
        
    async def __aenter__(self):
        if self._init_method == InitStrategy.START_TURN:
            await self._start_new_turn()
        elif self._init_method == InitStrategy.NO_PARTITION:
            pass
        else:
            raise ValueError(f"Invalid init method: {self._init_method}")
        if self._branch is None or self._turn is None:
            raise ValueError("Branch or turn not set")
        self._set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self._reset_context()
        if exc_type is not None:
            return False
        return True
    
    async def push(self, value: "Block | CONTEXT_MODEL | Blockable") -> "Block":
        if not self.can_push:
            raise ValueError("Cannot push to context")
        from promptview.prompt import Block
        if isinstance(value, Block):
            msg = self.context_model.from_block(value)
        elif hasattr(value, "block"):
            msg = self.context_model.from_block(value.block())
        else:
            msg = value
        saved_value = await msg.save(turn=self.turn.id, branch=self.branch.id)
        return saved_value.to_block(self)
        
    
    async def last(self, limit=10) -> "BlockList":
        if not self.can_push:
            raise ValueError("Cannot load last messages from context")
        from promptview.prompt.block6 import Block, BlockList
        records = await self.context_model.query(
            self.partition_id, 
            self.branch
        ).limit(limit).order_by("created_at", direction="asc")
        # with Block() as blocks:
        #     for r in reversed(records):
        #         blocks /= r.to_block()
        return BlockList([r.to_block(self) for r in records])
    
    
    
    
    
    
    
    
    

