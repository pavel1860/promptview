
import inspect
from abc import abstractmethod
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, List,
                    Literal, Optional, ParamSpec, Type, TypeVar, Union)

from promptview.llms.messages import ActionCall, MessageChunk
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.execution_context import (ExLifecycle,
                                                 PromptExecutionContext)
from promptview.utils.function_utils import call_function, filter_func_args
from pydantic import BaseModel, Field

HandlerTypes = Literal["prompt", "function", "async_generator"]



class BaseActionHandler(BaseModel):
    action: Type[BaseModel]
            
    @abstractmethod
    def call(self, action_call: ActionCall, ex_ctx: PromptExecutionContext)-> PromptExecutionContext:
        pass
    
    @abstractmethod
    def stream(self, action_call: ActionCall, ex_ctx: PromptExecutionContext)-> AsyncGenerator[MessageChunk, None]:
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
    
    async def call(self, action_call: ActionCall, ex_ctx: PromptExecutionContext) -> PromptExecutionContext:
        handler_kwargs = ex_ctx.kwargs | {"action": action_call.action}
        handler_kwargs = filter_func_args(self.handler, handler_kwargs)
        ex = ex_ctx.start_execution(
            prompt_name=action_call.name,
            kwargs=handler_kwargs,
            run_type="tool",
            action_call=action_call
        )
        ex.lifecycle_phase = ExLifecycle.COMPLETE
        response = await call_function(self.handler, **handler_kwargs)        
        ex_ctx.add_response(response)
        return ex_ctx
    
    def stream(self, action_call: ActionCall, ex_ctx: PromptExecutionContext):
        handler_kwargs = ex_ctx.kwargs | {"action": action_call.action}
        handler_kwargs = filter_func_args(self.handler, handler_kwargs)
        return self.handler(action_call.action, **ex_ctx.kwargs)
    


class PromptHandler(BaseActionHandler):
    prompt: "Prompt"
    
    
    @property
    def type(self) -> HandlerTypes:
        return "prompt"
    # def handler_type(self):
    #     return "prompt"
    
    async def call(self, action: BaseModel, ex_ctx: PromptExecutionContext)-> PromptExecutionContext:
        action_kwargs = action.model_dump()
        # handler_kwargs = filter_func_args(self.prompt._render_method, ex_ctx.kwargs | action_kwargs)
        handler_kwargs = ex_ctx.kwargs | action_kwargs
        return await call_function(self.prompt.call_ctx, action=action, ex_ctx=ex_ctx, **handler_kwargs)
    
    def stream(self, action: BaseModel, ex_ctx: PromptExecutionContext):
        action_kwargs = action.model_dump()
        handler_kwargs = ex_ctx.kwargs | action_kwargs | {"ex_ctx": ex_ctx}
        handler_kwargs = filter_func_args(self.prompt._render_method, handler_kwargs)
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