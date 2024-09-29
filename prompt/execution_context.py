import inspect
from abc import abstractmethod
from functools import wraps
from typing import (Any, Awaitable, Callable, Generic, List, Literal, Type,
                    TypedDict, TypeVar)

from promptview.llms.messages import AIMessage, BaseMessage, MessageChunk
from promptview.llms.tracer import RunTypes, Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import ViewBlock
from promptview.prompt.types import PromptInputs
from pydantic import BaseModel, Field


class BaseExecutionContext(BaseModel):
    name: str
    inputs: PromptInputs
    is_traceable: bool = True
    tracer_run: Tracer | None = None
    run_type: RunTypes
    
    class Config:
        arbitrary_types_allowed = True
    
    def __enter__(self):
        self.tracer_run = self.tracer()
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.end_run()
        if self.tracer_run:
            self.tracer_run.end_run(exc_type, exc_value, traceback)
        return False
    
    @abstractmethod
    def end_run(self):
        raise NotImplementedError("end_run method must be implemented")
    
    @abstractmethod
    def tracer(self):
        raise NotImplementedError("tracer method must be implemented")
    


class LlmExecutionContext(BaseExecutionContext):
    model: str
    messages: List[BaseMessage] | None = None
    actions: Actions | None = None
    response: AIMessage | None = None
    chunks: List[MessageChunk] | None = None
    run_type: RunTypes = "llm"
    
    
    def push_chunk(self, chunk: MessageChunk):
        if self.chunks is None:
            self.chunks = []
        self.chunks.append(chunk)

    def tracer(self):
        inputs = {}
        if self.inputs.message:
            inputs["message"] = self.inputs.message.content
        if self.inputs.kwargs:
            inputs["input"] = self.inputs.kwargs
        return Tracer(
            is_traceable=self.is_traceable,
            tracer_run=self.inputs.tracer_run,
            name=self.name,
            run_type=self.run_type,
            inputs=inputs
        )
    


class PromptExecutionContext(BaseExecutionContext):
    # name: str   
    # inputs: PromptInputs
    # is_traceable: bool = True
    root_block: ViewBlock | None = None    
    messages: List[BaseMessage] | None = None
    actions: Actions | None = None  
    chunks: List[MessageChunk] | None = None  
    # prompt_run: Tracer | None = None
    output: AIMessage | None = None   

    
    def push_chunk(self, chunk: MessageChunk):
        if self.chunks is None:
            self.chunks = []
        self.chunks.append(chunk)
    
    def copy_ctx(self, with_views=False, with_messages=False, with_tracer=False):
        ctx = PromptExecutionContext(
            name=self.name,
            is_traceable=self.is_traceable,
            inputs=self.inputs.model_copy(),
            run_type=self.run_type
        )        
        if with_views and self.root_block is not None:
            ctx.root_block = self.root_block.model_copy()
        if with_messages and self.messages is not None:
            ctx.messages = [m.model_copy() for m in self.messages]
        if with_tracer:
            ctx.tracer_run = self.tracer_run
        return ctx
    
    def end_run(self):
        if self.tracer_run and self.output:
            self.tracer_run.end(outputs={'output': self.output.raw})
        
    
    def extend_views(self, views: List[ViewBlock]):
        if self.root_block is None:
            raise ValueError("Root block is not set")
        self.root_block.extend(views)
        return self.root_block
    
    
    def tracer(self):
        inputs = {}
        if self.inputs.message:
            inputs["message"] = self.inputs.message.content
        if self.inputs.kwargs:
            inputs["input"] = self.inputs.kwargs
        return Tracer(
            is_traceable=self.is_traceable,
            tracer_run=self.inputs.tracer_run,
            name=self.name,
            run_type=self.run_type,
            inputs=inputs
        )
    
    