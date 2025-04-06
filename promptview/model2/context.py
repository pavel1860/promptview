
import contextvars
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Generic, Type, TypeVar

from pydantic import BaseModel

from promptview.model2.namespace_manager import NamespaceManager
from promptview.model2.versioning import ArtifactLog, Partition, UserContext
from promptview.tracer.langsmith_tracer import RunTypes
from ..tracer import Tracer

    

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
    RESUME_TURN = "resume_turn"
    
    

class Context(Generic[PARTITION_MODEL, CONTEXT_MODEL]):
    partition_model: Type[PARTITION_MODEL]
    context_model: Type[CONTEXT_MODEL]
    _partition_id: int | None
    
    _ctx_token: contextvars.Token | None
    _branch: "Branch | None"
    _turn: "Turn | None"
    _user: PARTITION_MODEL | None
    def __init__(
        self,
        user: PARTITION_MODEL,
        partition: "Partition", 
        branch: "int" = 1,
        span_name: str | None = None, 
        auto_commit: bool = True,
        user_context: UserContext | None = None
    ):
        # if isinstance(partition, int):
        #     self._partition_id = partition
        #     self._partition = None
        # elif partition is None:
        #     ctx = Context.get_current(raise_error=True)
        #     if ctx is None:
        #         raise ValueError("Context not set")
        #     self._partition = ctx.partition
        #     self._partition_id = ctx.partition_id
        # else:
            # self._partition_id = partition.id
        self._partition = partition
        self._user = user
        self._init_method = InitStrategy.RESUME_TURN        
        self._init_params = {"branch_id": branch if type(branch) is int else branch.id}
        self._ctx_token = None
        self._span_name = span_name
        self._branch = None
        self._turn = None
        self._auto_commit = auto_commit
        self._parent_ctx = None
        self._trace_id = None
        self._user_context = user_context
        self._tracer_run = None
        
        
    @property
    def trace_id(self):  
        if self._tracer_run is not None:      
            return str(self._tracer_run.id)
        return self._trace_id
    
    @trace_id.setter
    def trace_id(self, value: str):
        self._trace_id = value
        
        
    @property
    def tracer(self):
        if self._tracer_run is None:
            raise ValueError("Tracer not set")
        return self._tracer_run
    
    @property
    def user_context(self):
        if self._user_context is None:
            raise ValueError("User context not set")
        return self._user_context
    
    @user_context.setter
    def user_context(self, value: UserContext):
        self._user_context = value
        
    @property
    def user(self) -> PARTITION_MODEL:
        if self._user is None:
            raise ValueError("User not set")
        return self._user
        
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
        if self._partition is None:
            raise ValueError("Partition ID not set")
        return self._partition.id
    
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
    
    def start_turn(self, branch_id: int | None = None):
        if branch_id is None:
            branch_id = 1
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
        child = Context(user=self.user, partition=self.partition, span_name=span_name)
        child._branch = self._branch
        child._turn = self._turn
        child._parent_ctx = self
        return child
    
    async def _start_new_turn(self):
        if "branch_id" in self._init_params:
            branch = await NamespaceManager.get_branch(self._init_params["branch_id"])
            if branch is None:
                raise ValueError(f"Branch {self._init_params['branch_id']} not found")
            self._branch = branch
        self._turn = await NamespaceManager.create_turn(
            partition_id=self.partition_id,
            branch_id=self.branch.id,
            user_context=self._user_context
        )
        
    async def _resume_turn(self):
        if "branch_id" in self._init_params:
            branch = await NamespaceManager.get_branch(self._init_params["branch_id"])
            if branch is None:
                raise ValueError(f"Branch {self._init_params['branch_id']} not found")
            self._branch = branch
        self._turn = await NamespaceManager.get_last_turn(
            partition_id=self.partition_id,
            branch_id=self.branch.id
        )
        
    def _set_context(self):
        self._ctx_token = CURR_CONTEXT.set(self)
        
    def _reset_context(self):
        if self._ctx_token is not None:
            CURR_CONTEXT.reset(self._ctx_token)
        self._ctx_token = None
        
    def start_tracer(self, name: str, run_type: RunTypes = "prompt", inputs: dict[str, Any] | None = None):
        self._tracer_run = Tracer(
            name=name,
            run_type=run_type,
            inputs=inputs,
            is_traceable=True,
            tracer_run=self._parent_ctx._tracer_run if self._parent_ctx is not None else None,
        )
        return self
    
    async def _init(self):
        if self._init_method == InitStrategy.START_TURN:
            await self._start_new_turn()
        elif self._init_method == InitStrategy.NO_PARTITION:
            raise NotImplementedError("No partition")
        elif self._init_method == InitStrategy.RESUME_TURN:
            await self._resume_turn()
        else:
            raise ValueError(f"Invalid init method: {self._init_method}")
        
    async def __aenter__(self):
        await self._init()
        if self._branch is None or self._turn is None:
            raise ValueError("Branch or turn not set")
        self._set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self._reset_context()
        if self._tracer_run is not None:
            self._tracer_run.__exit__(exc_type, exc_value, traceback)
        if exc_type is not None:
            if self._parent_ctx is None:
                await self.revert(message=str(exc_value))
            return False
        if self._auto_commit and self._parent_ctx is None:
            await self.commit()
        return True
    
    
    async def commit(self):
        await ArtifactLog.commit_turn(
            turn_id=self.turn.id,             
            trace_id=self.trace_id,
        )
    
    async def revert(self, message: str | None = None):
        await ArtifactLog.revert_turn(
            turn_id=self.turn.id,
            message=message,
            trace_id=self.trace_id,
        )
    
    async def push(self, value: "Block | CONTEXT_MODEL | Blockable") -> "Block":
        if not self.can_push:
            raise ValueError("Cannot push to context")
        if not self.is_initialized:
            await self._init()
        from promptview.prompt import Block
        if isinstance(value, Block):
            msg = self.context_model.from_block(value)
        elif hasattr(value, "block"):
            msg = self.context_model.from_block(value.block())
        else:
            msg = value
        saved_value = await msg.save(turn=self.turn.id, branch=self.branch.id)
        return saved_value.to_block(self)
        
    
    async def last(self, limit=10, ) -> "BlockList":
        # if not self.can_push:
            # raise ValueError("Cannot load last messages from context")
        if not self.is_initialized:
            await self._init()
        from promptview.prompt.block6 import Block, BlockList
        records = await self.context_model.query(
            self.partition_id, 
            self.branch
        ).limit(limit).order_by("created_at", direction="asc")
        # with Block() as blocks:
        #     for r in reversed(records):
        #         blocks /= r.to_block()
        return BlockList([r.to_block(self) for r in records])
    
    
    
    
    
    
    
    
    

