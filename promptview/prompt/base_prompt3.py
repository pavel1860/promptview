import enum
import functools
import inspect
from functools import wraps
from typing import (Any, Awaitable, Callable, Concatenate, Generic, List, Literal, Type,
                    TypedDict, TypeVar, ParamSpec)

from promptview.conversation.history import History
from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.llm2 import LLM
from promptview.llms.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer2 import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.controller import Controller
from promptview.prompt.depends import Depends, DependsContainer, resolve_dependency
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.state.context import Context
from promptview.utils.function_utils import call_function
from pydantic import BaseModel, Field


P = ParamSpec('P')
R = TypeVar('R')


# class FunctionType(enum.Enum):
#     FUNCTION = 0
#     ASYNC_FUNCTION = 1
#     GENERATOR = 2
#     ASYNC_GENERATOR = 3
    


# def check_function_type(func):    
#     if inspect.isfunction(func):
#         return FunctionType.FUNCTION
#     elif inspect.iscoroutinefunction(func):
#         return FunctionType.ASYNC_FUNCTION
#     elif inspect.isgeneratorfunction(func):
#         return FunctionType.GENERATOR
#     elif inspect.isasyncgenfunction(func):
#         return FunctionType.ASYNC_GENERATOR
        



# class FunctionDescription:
#     """
#     container for function type and parameters
#     """
#     def __init__(self, func) -> None:
#         self.type = check_function_type(func)
#         self.params = [a for a in inspect.signature(func).parameters.values() if a.name != 'self']

#     def merge_args_kwargs(self, args, kwargs):
#         log_args = {}
#         for i, arg in enumerate(args):
#             log_args[self.params[i].name] = arg
#         log_args.update(kwargs)
#         return log_args
    
#     # def filter_args(self, args, kwargs):
        
        # return log_args, log_kwargs




    
    
    
    



class Prompt(Controller[P, R]):   
    
    
    async def _call_with_dependencies(self, *args, **kwargs):
        injection_kwargs = await self._inject_dependencies(*args, **kwargs)                      
        res = await call_function(self._complete, *args, **kwargs, **injection_kwargs)
        return res
    
    
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        inspect.signature(self._complete).bind(*args, **kwargs)
            # res = await self._call_with_dependencies(*args, **kwargs)
        injection_kwargs = await self._inject_dependencies(*args, **kwargs)        
        with Tracer(
                name=self._complete.__name__,
                run_type="prompt",
                inputs=self._filter_args_for_trace(*args, **kwargs, **injection_kwargs),
            ) as run:
            kwargs.update(injection_kwargs)
            try:
                res = await call_function(self._complete, *args, **kwargs)
                run.add_outputs({"response": self._sanitize_output(res)})
                return res
            except Exception as e:
                run.end(errors=str(e))
                raise e
        


        
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

