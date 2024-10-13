from typing import (Any, Coroutine, Generic, List, Literal, ParamSpec, Type,
                    TypeVar)

from promptview.llms.interpreter.messages import BaseMessage
from promptview.llms.tracing.tracer import Tracer
from promptview.prompt.view_block import ViewBlock
from promptview.state.context import Context
from pydantic import BaseModel, Field

ToolChoiceParam = Literal['auto', 'required', 'none'] | BaseModel | None


# RenderViewTypes = List[ViewBlock] | ViewBlock | BaseModel | List[str] | str

# RenderMethodOutput = Coroutine[Any, Any, RenderViewTypes] | Coroutine[Any, Any, tuple[RenderViewTypes, ...]] | RenderViewTypes | tuple[RenderViewTypes, ...]

T = TypeVar("T")
P = TypeVar("P")

class PromptInputs(BaseModel, Generic[P, T]):
    message: BaseMessage | None = None
    view_blocks: List[ViewBlock] | ViewBlock | None = None
    context: Context | None = None
    actions: List[Type[BaseModel]] | None = None
    tool_choice: ToolChoiceParam | None = None
    tracer_run: Tracer | None = None
    args: P
    kwargs: T
    
    class Config:
        arbitrary_types_allowed = True
        
        
        
RoleType = Literal["assistant", "user", "system", "tool"]
BulletType = Literal["number" , "astrix" , "dash" , "none", None] | str
StripType = Literal["left", "right"] | bool | None