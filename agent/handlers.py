
import inspect
from abc import abstractmethod
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, List,
                    Literal, Optional, ParamSpec, Type, TypeVar, Union)

from promptview.llms.messages import ActionCall, MessageChunk
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.execution_context import (Execution, ExecutionContext,
                                                 ExLifecycle)
from promptview.utils.function_utils import call_function, filter_func_args
from pydantic import BaseModel, Field

HandlerTypes = Literal["prompt", "function", "async_generator"]



class BaseActionHandler(BaseModel):
    action: Type[BaseModel]
            
    @abstractmethod
    def call(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> ExecutionContext:
        pass
    
    @abstractmethod
    def stream(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> AsyncGenerator[MessageChunk, None]:
        pass
    
    @property
    @abstractmethod
    def type(self) -> HandlerTypes:
        pass
    
    @abstractmethod
    def start_execution(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> Execution:
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
    def start_execution(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> Execution:
        execution = Execution(
            prompt_name=action_call.name,
            kwargs=ex_ctx.kwargs,
            run_type="tool",
            context=ex_ctx.context,
            parent_tracer_run=ex_ctx.curr_ex.tracer_run if ex_ctx.curr_ex else None,
            action_call=action_call,
            ex_type="tool",
        )
        execution.start()
        return execution
        
    
    async def call(self, action_call: ActionCall, ex_ctx: ExecutionContext) -> ExecutionContext:
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
    
    def stream(self, action_call: ActionCall, ex_ctx: ExecutionContext):
        handler_kwargs = ex_ctx.kwargs | {"action": action_call.action}
        handler_kwargs = filter_func_args(self.handler, handler_kwargs)
        return self.handler(action_call.action, **ex_ctx.kwargs)
    


class PromptHandler(BaseActionHandler):
    prompt: "Prompt"
    is_routing: bool = False
    
    
    @property
    def type(self) -> HandlerTypes:
        return "prompt"
    # def handler_type(self):
    #     return "prompt"
    
    def start_execution(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> Execution:
        pass
    
    async def call(self, action_call: ActionCall, ex_ctx: ExecutionContext)-> ExecutionContext:
        handler_kwargs = ex_ctx.kwargs | action_call.to_kwargs()
        handler_kwargs = filter_func_args(self.prompt._render_method, handler_kwargs)        
        prompt_ctx = ex_ctx.create_child(
            prompt_name=self.prompt._view_builder.prompt_name,
            ex_type="prompt" if self.is_routing else "tool",
            run_type="tool",
            kwargs=handler_kwargs,
            
        )
        prompt_ctx = await call_function(self.prompt.call_ctx, ex_ctx=prompt_ctx, **handler_kwargs)
        ex_ctx.merge_child(prompt_ctx)
        return ex_ctx
    
    
    async def stream(self, action_call: ActionCall, ex_ctx: ExecutionContext) -> AsyncGenerator[MessageChunk, None]:
        handler_kwargs = ex_ctx.kwargs | action_call.to_kwargs()
        handler_kwargs = filter_func_args(self.prompt._render_method, handler_kwargs)        
        prompt_ctx = ex_ctx.create_child(
            prompt_name=self.prompt._view_builder.prompt_name,
            ex_type="prompt" if self.is_routing else "tool",
            run_type="tool",
            kwargs=handler_kwargs,
            
        )
        async for msg in self.prompt.stream(ex_ctx=ex_ctx, **handler_kwargs):
            yield msg
    # def stream(self, action_call: ActionCall, ex_ctx: ExecutionContext):
    #     handler_kwargs = ex_ctx.kwargs | action_call.to_kwargs()
    #     handler_kwargs = filter_func_args(self.prompt._render_method, handler_kwargs)
    #     return self.prompt.stream(ex_ctx=ex_ctx, **handler_kwargs)


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
