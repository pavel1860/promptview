
import contextvars
from enum import StrEnum
from typing import TYPE_CHECKING, Generic, Type, TypeVar

from promptview.model2.namespace_manager import NamespaceManager

    

if TYPE_CHECKING:
    from promptview.model2.model import Model, ContextModel
    from promptview.model2.versioning import Branch, Turn
    from promptview.prompt.block6 import Block
    
PARTITION_MODEL = TypeVar("PARTITION_MODEL", bound="Model")
CONTEXT_MODEL = TypeVar("CONTEXT_MODEL", bound="ContextModel")


CURR_CONTEXT = contextvars.ContextVar("curr_context")

class InitStrategy(StrEnum):
    START_TURN = "start_turn"    
    BRANCH_FROM = "branch_from"
    

class Context(Generic[PARTITION_MODEL, CONTEXT_MODEL]):
    partition_model: Type[PARTITION_MODEL]
    context_model: Type[CONTEXT_MODEL]
    _partition_id: int | None
    
    _ctx_token: contextvars.Token | None
    _branch: "Branch | None"
    _turn: "Turn | None"
    
    def __init__(self, partition_id: int | None = None, span_name: str | None = None):
        self._partition_id = partition_id
        self._init_method = None
        self._init_params = {}
        self._ctx_token = None
        self._span_name = span_name
        
    @classmethod
    def get_current(cls, raise_error: bool = True):
        ctx = CURR_CONTEXT.get()
        if ctx is None:
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
    
    
    def start_turn(self, branch_id: int = 1):
        self._init_method = InitStrategy.START_TURN
        self._init_params["branch_id"] = branch_id
        return self
        
    
    def branch_from(self, turn_id: int):
        self._init_method = InitStrategy.BRANCH_FROM
        self._init_params["turn_id"] = turn_id
        return self
    
    def build_child(self, span_name: str | None = None):
        child = Context(self.partition_id, span_name)
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
        else:
            raise ValueError(f"Invalid init method: {self._init_method}")
        self._set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self._reset_context()
        return self
    
    async def push(self, value: "Block | CONTEXT_MODEL") -> "Block":
        from promptview.prompt.block6 import Block
        if isinstance(value, Block):
            msg = self.context_model.from_block(value)
        else:
            msg = value
        saved_value = await msg.save(turn=self.turn.id, branch=self.branch.id)
        return saved_value.to_block()
        
    
    async def last(self, limit=10) -> "Block":
        from promptview.prompt.block6 import Block
        records = await self.context_model.query(
            self.partition_id, 
            self.branch
        ).limit(limit).order_by("created_at", ascending=False)
        with Block() as blocks:
            for r in reversed(records):
                blocks /= r.to_block()
        return blocks