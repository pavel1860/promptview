import inspect
from abc import abstractmethod
from functools import wraps
from typing import (Any, Awaitable, Callable, Generic, List, Literal, Type,
                    TypedDict, TypeVar)

from promptview.llms.messages import (ActionMessage, AIMessage, BaseMessage,
                                      HumanMessage, MessageChunk)
from promptview.llms.tracer import RunTypes, Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.prompt.types import PromptInputs
from pydantic import BaseModel, Field


class BaseExecutionContext(BaseModel):
    name: str
    inputs: PromptInputs
    is_traceable: bool = True
    tracer_run: Tracer | None = None
    run_type: RunTypes
    children: List["BaseExecutionContext"] = []
    parent: Any | None = None
    
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
    root_block: ViewBlock = Field(default_factory=lambda: create_view_block([], "root"))
    messages: List[BaseMessage] | None = None
    actions: Actions | None = None  
    chunks: List[MessageChunk] | None = None  
    # prompt_run: Tracer | None = None
    output: AIMessage | None = None   
    action_calls: List[BaseModel] = []

    
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
        parent_tracer = None
        if self.parent:
            parent_tracer = self.parent.tracer_run
        return Tracer(
            is_traceable=self.is_traceable,
            tracer_run=parent_tracer,
            name=self.name,
            run_type=self.run_type,
            inputs=inputs
        )
        
        
    def merge_ctx(self, ex_ctx: "PromptExecutionContext"):
        if ex_ctx.root_block is None:
            raise ValueError("Root block is not set")
        if self.root_block is None:
            self.root_block = ex_ctx.root_block.model_copy()
        else:
            self.extend_views(ex_ctx.root_block.view_blocks)
        if ex_ctx.output:
            if self.output:
                raise ValueError("Output is already set")
            self.output = ex_ctx.output.model_copy()
            # self.root_block.push(create_view_block(ex_ctx.output, ex_ctx.name + '_output'))
            
    
            
    def add_view(self, view: ViewBlock | HumanMessage | AIMessage | ActionMessage):
        if not isinstance(view, ViewBlock):
            view = create_view_block(view, self.name +"_" + view.role + '_output')
        self.root_block.add(view)
    
    def push_response(self, view: ViewBlock | AIMessage):
        if isinstance(view, AIMessage):
            if self.output is not None:
                raise ValueError("Output is already set")
            self.output = view
            if view.action_calls:
                self.action_calls.extend([a.model_copy() for a in view.action_calls])
        else:
            raise ValueError("Invalid Response view type")
        # self.root_block.add(view)
    
    
    def top_response(self):
        if self.output:
            return True
        return False
    
    def pop_response(self):
        if not self.output:
            raise ValueError("Output is not set")
        response = self.output
        self.root_block.push(create_view_block(self.output, self.name + '_output'))
        self.output = None
        return response