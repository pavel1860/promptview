import enum
import functools
import inspect
from functools import wraps
from typing import (Any, Awaitable, Callable, Concatenate, Dict, Generic, List, Literal, Type,
                    TypedDict, TypeVar, ParamSpec)

from promptview.conversation.history import History
from promptview.llms.llm3 import LLM

from .block import BaseBlock
from .context import BlockStream
from .depends import Depends, DependsContainer, resolve_dependency
from .mvc import ViewBlock, create_view_block
from .context import Context
from ..utils.function_utils import call_function, filter_args_by_exclude
from pydantic import BaseModel, Field


P = ParamSpec('P')
R = TypeVar('R')




class Controller(Generic[P, R]):
    _name: str
    _complete: Callable[P, R]
    
    
    def _set_history(self, history: History):
        history.init_last_session()
        return history
    
    
    def _filter_args_for_trace(self, *args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        _args, _kwargs = filter_args_by_exclude(args, kwargs, (LLM, Context, BlockStream))
        return {"args": _args, "kwargs": _kwargs}
    
    
    def _sanitize_output(self, output: Any) -> Any:
        if isinstance(output, BaseBlock):
            return output.content
        return output
    
    def build_execution_ctx(self) -> Context:
        curr_ctx = Context.get_current()
        ctx = curr_ctx.build_child(self._name)
        return ctx

    async def _inject_dependencies(self, *args: P.args, **kwargs: P.kwargs) -> Dict[str, Any]:
        signature = inspect.signature(self._complete)
        injection_kwargs = {}
        for param_name, param in signature.parameters.items():
            default_val = param.default
            if isinstance(default_val, DependsContainer):
                dependency_func = default_val.dependency
                resolved_val = await resolve_dependency(dependency_func,  *args, **kwargs)
                if isinstance(resolved_val, History):
                    resolved_val = self._set_history(resolved_val)
                injection_kwargs[param_name] = resolved_val            
                
        return injection_kwargs