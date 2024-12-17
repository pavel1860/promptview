import inspect
from functools import wraps
from typing import (Any, Awaitable, Callable, Generic, List, Literal, Type,
                    TypedDict, TypeVar, ParamSpec)

from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.llm2 import LLM
from promptview.llms.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.state.context import Context
from promptview.utils.function_utils import call_function
from pydantic import BaseModel, Field


P = ParamSpec('P')
R = TypeVar('R')


class Prompt(Generic[P, R]):
    _name: str
    _complete: Callable[P, R]
    # async def complete(self, *args: P.args, **kwargs: P.kwargs) -> T:
    #     raise NotImplementedError()
    
    
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        with Tracer(
                name=self._complete.__name__,
                # is_traceable=is_traceable,
                is_traceable=True,
                inputs=kwargs,
                # session_id=context.session_id,
                # tracer_run=tracer_run
            ) as run:
            res = await self._complete(*args, **kwargs)
            run.add_outputs({"response":res})
            return res
    

        
def prompt(
    **kwargs: Any
)-> Callable[[Callable[P, R]], Prompt[P, R]]:
    
    def decorator(func: Callable[P, R]) -> Prompt[P,R]:
        prompt = Prompt(
                # model=model, #type: ignore                
                **kwargs
            )
        prompt._name=func.__name__
        prompt._complete = func
        return prompt        
    return decorator