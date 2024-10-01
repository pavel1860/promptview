import inspect
from functools import wraps
from typing import (Any, AsyncGenerator, Awaitable, Callable, Generic, List,
                    Literal, ParamSpec, Type, TypedDict, TypeVar)

from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.llm2 import LLM
from promptview.llms.messages import (AIMessage, BaseMessage, HumanMessage,
                                      MessageChunk)
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.execution_context import PromptExecutionContext
from promptview.prompt.mvc import (RenderMethodOutput, ViewBlock,
                                   create_view_block)
from promptview.prompt.types import PromptInputs, ToolChoiceParam
from promptview.prompt.view_builder import ViewBlockBuilder
from promptview.state.context import Context
from promptview.utils.function_utils import call_function
from pydantic import BaseModel, Field

P = ParamSpec("P")
R = TypeVar("R")  





class Prompt(BaseModel, Generic[P]):    
    is_traceable: bool = True
    llm: LLM = Field(default_factory=OpenAiLLM)
    tool_choice: ToolChoiceParam = None
    actions: List[Type[BaseModel]] | None = []
    _render_method: Callable[P, RenderMethodOutput] | None = None
    _output_parser_method: Callable | None = None
    _view_builder: ViewBlockBuilder
    
    _name: str | None = None
    
    
    def __init__(self, **data):
        super().__init__(**data)
        self._view_builder = ViewBlockBuilder(prompt_name="render_" + self._name if self._name else self.__class__.__name__)
    
    
    async def render(self, *args: P.args, **kwargs: P.kwargs) -> RenderMethodOutput:
        if self._render_method is None:
            raise NotImplementedError("Render method is not implemented")
        return await call_function(self._render_method, *args, **kwargs)
    
    async def parse(self, response: AIMessage, messages: List[BaseMessage], actions: Actions, **kwargs: Any) -> AIMessage:
        return response
    
    
    def build_execution_context(
            self,
            *args: Any,
            message: str | BaseMessage | None = None,
            views: List[ViewBlock] | ViewBlock | None = None, 
            context: Context | None = None, 
            actions: List[Type[BaseModel]] | None = None,
            tool_choice: ToolChoiceParam = None,
            tracer_run: Tracer | None=None,            
            ex_ctx: PromptExecutionContext | None = None,
            **kwargs: Any
            # *args: P.args,
            # **kwargs: P.kwargs
        ) -> PromptExecutionContext:
        if message is not None:
            message = HumanMessage(content=message) if isinstance(message, str) else message        
        prompt_inputs = PromptInputs(
            message=message,
            view_blocks=views,
            context=context,
            actions=actions or self.actions,
            tool_choice=tool_choice or self.tool_choice,
            tracer_run=tracer_run,
            args=args,
            kwargs=kwargs
        )
        ex_ctx_inst = PromptExecutionContext(
            name=self._view_builder.prompt_name,
            is_traceable=self.is_traceable,
            inputs=prompt_inputs,
            run_type="prompt",            
        )
        if ex_ctx:
            ex_ctx_inst.parent = ex_ctx
            ex_ctx_inst.root_block = ex_ctx.root_block.model_copy()
        return ex_ctx_inst
        
    
    async def call_render(self, ex_ctx: PromptExecutionContext) -> ViewBlock:
        views = await call_function(
                # self.render if self._render_method is None else self._render_method, 
                self.render,
                **ex_ctx.inputs.kwargs
            )        
        # view_block = await self.transform(views, context=context, **kwargs)
        return views
    
    
    def call_llm_transform(self, ex_ctx: PromptExecutionContext) -> PromptExecutionContext:
        if not ex_ctx.root_block:
            raise ValueError("Root block is not set")
        messages, actions = self.llm.transform(
                root_block=ex_ctx.root_block, 
                actions=ex_ctx.inputs.actions, 
                context=ex_ctx.inputs.context, 
                **ex_ctx.inputs.kwargs
            )
        ex_ctx.messages = messages
        ex_ctx.actions = actions
        return ex_ctx
    
    
    async def transform(
        self, 
        ex_ctx: PromptExecutionContext
    ) -> PromptExecutionContext:
        
        system_view = await self._view_builder.get_template_views(self, **ex_ctx.inputs.kwargs)
        if system_view:
            ex_ctx.root_block.add(system_view)
        render_output = await self.call_render(ex_ctx)
        views = await self._view_builder.process_render_output(render_output)
        ex_ctx.root_block.add(views)
        # if isinstance(views, list):
        #     ex_ctx.root_block.extend(views)        
        # elif isinstance(views,ViewBlock):
        #     ex_ctx.root_block.push(views)
        # else:
            # raise ValueError(f"Invalid views: {type(views)}")
        
        return ex_ctx
    
    async def call_llm_complete(self, ex_ctx: PromptExecutionContext) -> PromptExecutionContext:
        if not ex_ctx.messages:
            raise ValueError("No messages to complete")        
        response = await self.llm.complete(
            messages=ex_ctx.messages, 
            actions=ex_ctx.actions, 
            tool_choice=ex_ctx.inputs.tool_choice, 
            tracer_run=ex_ctx.tracer_run, 
            **ex_ctx.inputs.kwargs
        )
        ex_ctx.push_response(response)
        return ex_ctx
    
    async def call_parse(self, ex_ctx: PromptExecutionContext) -> AIMessage:
        if self._output_parser_method:
            response = await call_function(self._output_parser_method, ex_ctx.output, ex_ctx.messages, ex_ctx.actions, **ex_ctx.inputs.kwargs)
        else:
            response = await call_function(self.parse, ex_ctx.output, ex_ctx.messages, ex_ctx.actions, **ex_ctx.inputs.kwargs)            
        return response
    
    
    async def complete(
            self, 
            message: str | BaseMessage | None = None,
            views: List[ViewBlock] | ViewBlock | None = None, 
            context: Context | None = None, 
            actions: List[Type[BaseModel]] | None = None,
            tool_choice: ToolChoiceParam = None,
            tracer_run: Tracer | None=None,
            *args: P.args, 
            **kwargs: P.kwargs
        ) -> AIMessage:
        with self.build_execution_context(
            *args, 
            message=message,
            views=views,
            context=context,
            actions=actions,
            tool_choice=tool_choice,
            tracer_run=tracer_run,            
            **kwargs) as ex_ctx:
            if not ex_ctx.root_block:
                ex_ctx = await self.transform(ex_ctx)
            if not ex_ctx.messages:
                ex_ctx = self.call_llm_transform(ex_ctx)
            if not ex_ctx.output:
                ex_ctx = await self.call_llm_complete(ex_ctx)                    
            if not ex_ctx.output:
                raise ValueError("No output from the prompt")
            return ex_ctx.output
        
        
    async def call_ctx(
            self, 
            ex_ctx: PromptExecutionContext | None = None,
            *args: P.args, 
            **kwargs: P.kwargs
        ) -> PromptExecutionContext:
        # parent_ctx = ex_ctx
        # if not ex_ctx:
            # ex_ctx = self.build_execution_context(*args, **kwargs)
        # with ex_ctx:
        with self.build_execution_context(
            ex_ctx=ex_ctx,
            *args, 
            **kwargs
            ) as ex_ctx:
        
            if not ex_ctx.root_block:
                ex_ctx = await self.transform(ex_ctx)
            if not ex_ctx.messages:
                ex_ctx = self.call_llm_transform(ex_ctx)
            if ex_ctx.output:
                raise ValueError("Output already set")
            ex_ctx = await self.call_llm_complete(ex_ctx)
            if not ex_ctx.output:
                raise ValueError("No output from the prompt execution")
            return ex_ctx
    
    
    async def __call__(
            self, 
            *args: P.args, 
            **kwargs: P.kwargs
        ) -> AIMessage:
        with self.build_execution_context(
            *args, 
            **kwargs
            ) as ex_ctx:
            if not ex_ctx.root_block:
                ex_ctx = await self.transform(ex_ctx)
            if not ex_ctx.messages:
                ex_ctx = self.call_llm_transform(ex_ctx)
            if not ex_ctx.output:
                ex_ctx = await self.call_llm_complete(ex_ctx)                    
            if not ex_ctx.output:
                raise ValueError("No output from the prompt")
            return ex_ctx.output
        

        
    async def stream(
            self,             
            *args: P.args, 
            **kwargs: P.kwargs
        ) -> AsyncGenerator[MessageChunk, None]:
        
        with self.build_execution_context(
            *args, 
            **kwargs
        ) as ex_ctx:
                if not ex_ctx.root_block:
                    ex_ctx = await self.transform(ex_ctx)
                if not ex_ctx.messages:
                    ex_ctx = self.call_llm_transform(ex_ctx)
                if not ex_ctx.messages:
                    raise ValueError("No messages to stream")
                async for chunk in self.llm.stream(
                        messages=ex_ctx.messages, 
                        actions=ex_ctx.actions, 
                        tool_choice=ex_ctx.inputs.tool_choice, 
                        tracer_run=ex_ctx.tracer_run, 
                        **ex_ctx.inputs.kwargs
                    ):
                    # ex_ctx.push_chunk(chunk)
                    if not chunk.did_finish:
                        yield chunk
        return

        
    # async def run_steps(self, ex_ctx: PromptExecutionContext)-> PromptExecutionContext:
    #     # with self.build_tracer(ex_ctx) as prompt_run:
    #     with ex_ctx.tracer() as prompt_run:
    #         try:
    #             ex_ctx.prompt_run = prompt_run
    #             if not ex_ctx.root_block:
    #                 ex_ctx = await self.view_step(ex_ctx)
    #             if not ex_ctx.messages:
    #                 ex_ctx = self.messages_step(ex_ctx)
    #             ex_ctx = await self.complete_step(ex_ctx)
    #             if not ex_ctx.output:
    #                 raise ValueError("No output from the prompt")
    #             prompt_run.end(outputs={'output': ex_ctx.output.raw})
    #             # prompt_run.end(outputs={'output': ex_ctx.output.to_langsmith()})
    #             return ex_ctx
    #         except Exception as e:
    #             prompt_run.end(errors=str(e))
    #             raise e
        
    # async def parse_output(self, response: AIMessage, messages: List[BaseMessage], actions: Actions, **kwargs: Any):
    #     if self._output_parser_method:
    #         await call_function(self._output_parser_method, response, messages, actions, **kwargs)
    #     return response
    
    async def display(self, *args, **kwargs):
        from IPython.display import Markdown, display
        ex_ctx = await self.to_ex_ctx(*args, **kwargs)
        if not ex_ctx.messages:
            raise ValueError("No messages to display")
        for msg in ex_ctx.messages:            
            print(f"-----------------------{msg.role} message----------------------") #type: ignore
            print(msg.content)
            # display(Markdown(msg.content))
        
    
        
    async def to_ex_ctx(
        self,
        *args: Any,
        **kwargs: Any
    ):
        ex_ctx = self.build_execution_context(*args, **kwargs)
        if not ex_ctx.root_block:
            ex_ctx = await self.transform(ex_ctx)
        if not ex_ctx.messages:
            ex_ctx = self.call_llm_transform(ex_ctx)
        return ex_ctx
    
    
    
    
    # async def view_step(self, ex_ctx: PromptExecutionContext):
    #     root_block = await self.handle_render(
    #         views=ex_ctx.inputs.view_blocks, 
    #         context=ex_ctx.inputs.context, 
    #         message=ex_ctx.inputs.message, 
    #         **ex_ctx.inputs.kwargs
    #     )
    #     ex_ctx.root_block = root_block
    #     return ex_ctx

    
    # def messages_step(self, ex_ctx: PromptExecutionContext):
    #     if not ex_ctx.root_block:
    #         raise ValueError("Root block is not set")
    #     messages, actions = self.llm.transform(
    #             root_block=ex_ctx.root_block, 
    #             actions=ex_ctx.inputs.actions, 
    #             context=ex_ctx.inputs.context, 
    #             **ex_ctx.inputs.kwargs
    #         )
    #     ex_ctx.messages = messages
    #     ex_ctx.actions = actions
    #     return ex_ctx
    
    # async def complete_step(self, ex_ctx: PromptExecutionContext):
    #     if not ex_ctx.messages:
    #         raise ValueError("No messages to complete")
        
    #     response = await self.llm.complete(
    #         messages=ex_ctx.messages, 
    #         actions=ex_ctx.actions, 
    #         tool_choice=ex_ctx.inputs.tool_choice, 
    #         tracer_run=ex_ctx.prompt_run, 
    #         **ex_ctx.inputs.kwargs
    #     )
    #     ex_ctx.output = response
    #     return ex_ctx
            
    def set_methods(self, render_func: Callable[P, RenderMethodOutput] | None = None, output_parser: Callable | None = None) -> None:
        self._render_method = render_func
        self._output_parser_method = output_parser
    
        
    # async def to_views(
    #     self,
    #     message: str | BaseMessage | None = None,        
    #     views: List[ViewBlock] | ViewBlock | None = None, 
    #     actions: List[Type[BaseModel]] | None = None,
    #     **kwargs: Any
    # ):
    #     if message is not None:
    #         message = HumanMessage(content=message) if isinstance(message, str) else message
    #     actions = actions or self.actions
    #     views = views or await self.handle_render(message=message, **kwargs)
    #     view_block = await self.transform(views, **kwargs)        
    #     return view_block
        
    # async def to_messages(
    #     self,
    #     actions: List[Type[BaseModel]] | None = None,
    #     **kwargs: Any
    # ):
    #     view_block = await self.to_views(actions=actions, **kwargs)
    #     messages, actions = self.llm.transform(view_block, actions=actions, **kwargs)                
    #     return messages
        
        
    # @classmethod
    # def decorator_factory(cls) -> Callable[..., Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]]:
    #     # Define the decorator with kwargs
    #     def prompt_decorator(**kwargs: cls):
    #         # Define the actual decorator
    #         def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    #             # Create a prompt instance with the given kwargs
    #             prompt = cls[T](**kwargs)
    #             prompt.set_methods(func)
                
    #             @wraps(func)
    #             async def wrapper(*args, **inner_kwargs) -> T:
    #                 # Call the prompt instance with necessary arguments
    #                 return await prompt(*args, **inner_kwargs)
                
    #             return wrapper
            
    #         return decorator

    #     return prompt_decorator
    
    

    # @classmethod
    # def decorator_factory(cls):
    #     def prompt_decorator( 
    #         self=None,   
    #         model: str = "gpt-4o",
    #         llm: LLM | None = None,            
    #         parallel_actions: bool = True,
    #         is_traceable: bool = True,
    #         output_parser: Callable[[AIMessage], T] | None = None,
    #         tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,
    #         actions: List[Type[BaseModel]] | None = None,
    #         **kwargs: Any
    #     ):
    #         if llm is None:
    #             if model.startswith("gpt"):
    #                 llm = OpenAiLLM(
    #                     model=model, 
    #                     parallel_tool_calls=parallel_actions
    #                 )
    #             elif model.startswith("claude"):
    #                 llm = AnthropicLLM(
    #                     model=model, 
    #                     parallel_tool_calls=parallel_actions
    #                 )
    #         def decorator(func) -> Callable[..., Awaitable[T]]:
    #             prompt = cls[T](
    #                     model=model,
    #                     llm=llm,                        
    #                     tool_choice=tool_choice,
    #                     actions=actions,
    #                     is_traceable=is_traceable,
    #                     **kwargs
    #                 )
    #             prompt._name=func.__name__
    #             prompt.set_methods(func, output_parser)
    #             if self:
    #                 self.router_prompt = prompt
    #             # @wraps(func)
    #             # async def wrapper(**kwargs) -> T:            
    #             #     return await prompt(**kwargs)
    #             return prompt
                    
                
    #             # wrapper.__signature__ = sig
    #             return wrapper
            
    #         return decorator
    #     return prompt_decorator




