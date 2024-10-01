
import inspect
from abc import abstractmethod
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, List,
                    Literal, Optional, ParamSpec, Type, TypeVar, Union)

from promptview.llms.messages import MessageChunk
from promptview.prompt.base_prompt import Prompt
from promptview.utils.function_utils import call_function, filter_func_args
from pydantic import BaseModel, Field

HandlerTypes = Literal["prompt", "function", "async_generator"]



class BaseActionHandler(BaseModel):
    action: Type[BaseModel]
            
    @abstractmethod
    def call(self, action: BaseModel, **kwargs):
        pass
    
    @abstractmethod
    def stream(self, action: BaseModel, **kwargs)-> AsyncGenerator[MessageChunk, None]:
        pass
    
    @property
    @abstractmethod
    def type(self) -> HandlerTypes:
        pass


class FunctionHandler(BaseActionHandler):
    handler: Callable
    
    @property
    def type(self) -> HandlerTypes:
        if inspect.isasyncgenfunction(self.handler):
            return "async_generator"
        elif inspect.isfunction(self.handler):
            return "function"
        else:
            raise ValueError(f"Invalid handler type: {self.handler}")
    
    # def handler_type(self):
    #     if inspect.isasyncgenfunction(self.handler):
    #         return "async_generator"
    #     elif inspect.isfunction(self.handler):
    #         return "function"
    
    async def call(self, action: BaseModel, **kwargs):
        return await call_function(self.handler, action=action, **kwargs)
    
    def stream(self, action: BaseModel, **kwargs):
        return self.handler(action, **kwargs)
    


class PromptHandler(BaseActionHandler):
    prompt: "Prompt"
    
    
    @property
    def type(self) -> HandlerTypes:
        return "prompt"
    # def handler_type(self):
    #     return "prompt"
    
    async def call(self, action: BaseModel, **kwargs):
        return await call_function(self.prompt, action=action, **kwargs)
    
    def stream(self, action: BaseModel, **kwargs):
        action_kwargs = action.model_dump()
        handler_kwargs = filter_func_args(self.prompt._render_method, kwargs | action_kwargs)
        return self.prompt.stream(**handler_kwargs)


class ActionHandler(BaseModel):
    action: Type[BaseModel]
    handler: Callable
    is_prompt: bool = False
    is_stream: bool = False
    type: HandlerTypes
    
    
    def __init__(self, **data):
        handler_type = None
        handler = data.get("handler")
        if inspect.isasyncgenfunction(handler):
            handler_type = "async_generator"
        elif inspect.isfunction(handler):
            handler_type = "function"
        elif isinstance(handler, Prompt):
            if data.get("is_stream"):
                handler_type = "async_generator"
            else:
                handler_type = "function"
        else:
            raise ValueError(f"Invalid handler type: {handler}")
        data["type"] = handler_type
        super().__init__(**data)
        
    def filter_handler_args(self, kwargs):
        return filter_func_args(self.handler, kwargs)
        
    async def call(self, action, **kwargs):
        handler_kwargs = self.filter_handler_args({
            "action": action, 
        } | kwargs)
        return await call_function(self.handler, **handler_kwargs)
    
    def stream(self, action: BaseModel, **kwargs):
        if self.is_prompt:
            action_kwargs = action.model_dump()
            handler_kwargs = filter_func_args(self.handler._render_method, kwargs | action_kwargs)
            return self.handler.stream(**handler_kwargs)
        else:
            handler_kwargs = filter_func_args(self.handler,{
                "action": action, 
            } | kwargs)
            return self.handler(**handler_kwargs)
