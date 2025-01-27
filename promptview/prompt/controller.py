import enum
import functools
import inspect
from functools import wraps
from typing import (Any, Awaitable, Callable, Concatenate, Dict, Generic, List, Literal, Type,
                    TypedDict, TypeVar, ParamSpec)

from promptview.conversation.history import History
from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.llm2 import LLM
from promptview.llms.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.depends import Depends, DependsContainer, resolve_dependency
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.state.context import Context
from promptview.utils.function_utils import call_function
from pydantic import BaseModel, Field


P = ParamSpec('P')
R = TypeVar('R')




class Controller(Generic[P, R]):
    _name: str
    _complete: Callable[P, R]
    
    
    def _set_history(self, history: History):
        history.init_last_session()
        return history
    

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