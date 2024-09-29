from typing import (Any, Coroutine, Generic, List, Literal, ParamSpec, Type,
                    TypeVar)

from promptview.llms.messages import BaseMessage
from promptview.llms.tracer import Tracer
from promptview.prompt.mvc import ViewBlock
from promptview.state.context import Context
from pydantic import BaseModel, Field

ToolChoiceParam = Literal['auto', 'required', 'none'] | BaseModel | None


RenderViewTypes = List[ViewBlock] | ViewBlock | List[str] | str

RenderMethodOutput = Coroutine[Any, Any, RenderViewTypes] | RenderViewTypes

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