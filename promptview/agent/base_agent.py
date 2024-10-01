
import inspect
from functools import wraps
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, List,
                    Literal, Optional, ParamSpec, Type, TypeVar, Union)

from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.llm2 import LLM
from promptview.llms.messages import (ActionCall, ActionMessage, AIMessage,
                                      HumanMessage)
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer import Tracer
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.chat_prompt import ChatPrompt
from promptview.prompt.decorator import prompt
from promptview.prompt.execution_context import PromptExecutionContext
from promptview.prompt.types import RenderMethodOutput, ToolChoiceParam
from promptview.state.context import Context
from promptview.utils.function_utils import call_function, filter_func_args
from pydantic import BaseModel, Field

HandlerTypes = Literal["prompt", "function", "async_generator"]

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

    
P = ParamSpec("P")
R = TypeVar("R")  

# class Agent(Prompt[P], Generic[P]):
class Agent(ChatPrompt[P], Generic[P]):
    iterations: int = 1
    add_input_history: bool = False 
    is_router: bool = False
    _action_handlers: Dict[str, ActionHandler] = {}

    def handle(self, action: Type[BaseModel], handler: Callable, is_stream: bool = False):
        action_handler = ActionHandler(
                            handler=handler,
                            action=action,
                            is_prompt=isinstance(handler, Prompt),
                            is_stream=is_stream
                        )
        self._action_handlers[action.__name__] =  action_handler
        
    
    def get_action_handler(self, action_call: ActionCall):
        handler = self._action_handlers[action_call.action.__class__.__name__]
        if not handler:
            raise ValueError(f"Action handler not found for {action_call.action.__class__.__name__}")
        return handler
    
    
    def process_action_output(self, ex_ctx: PromptExecutionContext ,action_call: ActionCall, action_output)-> PromptExecutionContext:
        if type(action_output) == str:
            action_output_str = action_output
        elif isinstance(action_output, BaseModel):
            action_output_str = action_output.model_dump_json()
        else:
            raise ValueError(f"Invalid action output ({type(action_output)}): {action_output}")
        message = ActionMessage(
                id=action_call.id,
                content=action_output_str,
                # tool_call=response.tool_calls[i]
            )
        ex_ctx.add_view(message)
        return ex_ctx
        
    def route(self, action: Type[BaseModel], prompt: Prompt, stream: bool = False):
        self.handle(action, prompt, is_stream=stream)                        
    
    
    
    async def call_agent_prompt(self, ex_ctx: PromptExecutionContext):
        sub_ctx = await call_function(
                self.call_ctx,
                ex_ctx=ex_ctx,
                *ex_ctx.inputs.args,
                **ex_ctx.inputs.kwargs
            ) 
        ex_ctx.push_response(sub_ctx.output)
        return ex_ctx
        
        
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[AIMessage, None]:
        with self.build_execution_context(
                *args, 
                **kwargs
                ) as ex_ctx:
            action_output = None
            ex_ctx = await self.transform(ex_ctx)
            for i in range(self.iterations):
                ex_ctx = await self.call_agent_prompt(ex_ctx)                
                if ex_ctx.top_response():
                    yield ex_ctx.pop_response()
                for action_call in ex_ctx.iter_action_calls():
                    action_handler = self.get_action_handler(action_call)                        
                    if action_handler.type == "async_generator":
                        stream_gen = action_handler.stream(action_call.action, **kwargs) #type: ignore
                        async for output in stream_gen:
                            if output is None:
                                break
                            yield output
                    elif action_handler.type == "function":
                        action_output = await action_handler.call(action_call.action, **kwargs)
                    else:
                        raise ValueError(f"Invalid action handler type: {action_handler.type}")                        
                    if action_output:
                        if isinstance(action_output, AIMessage):
                            yield action_output
                        else:
                            ex_ctx = self.process_action_output(ex_ctx, action_call, action_output)
                    else:
                        return
                else:
                    break
                    


    def reducer(self, action: Type[BaseModel]):
        def decorator(func):
            self.handle(action, func)
            return func
        return decorator
    
    




T = ParamSpec("T")
def agent(
    model: str = "gpt-4o",
    llm: LLM | None = None,
    parallel_actions: bool = True,
    is_traceable: bool = True,
    output_parser: Callable[[AIMessage], R] | None = None,
    tool_choice: ToolChoiceParam = None,
    actions: List[Type[BaseModel]] | None = None,
    iterations: int = 1,
    **kwargs: Any
):
    if llm is None:
        if model.startswith("gpt"):
            llm = OpenAiLLM(
                model=model, 
                parallel_tool_calls=parallel_actions
            )
        elif model.startswith("claude"):
            llm = AnthropicLLM(
                model=model, 
                parallel_tool_calls=parallel_actions
            )
    def decorator(func: Callable[T, RenderMethodOutput]) -> Agent[T]:
        agent_ins = Agent(
                model=model, #type: ignore
                llm=llm,                        
                tool_choice=tool_choice or Agent.model_fields.get("tool_choice").default,
                actions=actions,
                is_traceable=is_traceable,
                iterations=iterations,
                **kwargs
            )
        agent_ins._name=func.__name__
        agent_ins.set_methods(func, output_parser)            
        return agent_ins        
    return decorator


# def agent(
#     model: str = "gpt-4o",
#     llm: LLM | None = None,
#     parallel_actions: bool = True,
#     is_traceable: bool = True,
#     output_parser: Callable[[AIMessage], R] | None = None,
#     tool_choice: ToolChoiceParam = None,
#     actions: List[Type[BaseModel]] | None = None,
#     **kwargs: Any
# ):
#     def decorator(func: Callable[P, RenderMethodOutput]) -> Agent[P]:
#         agent_inst = Agent(
#                 model=model, #type: ignore
#                 llm=llm,                        
#                 tool_choice=tool_choice or ChatPrompt.model_fields.get("tool_choice").default,
#                 actions=actions,
#                 is_traceable=is_traceable,
#                 **kwargs
#             )
        
#         agent_inst._name=func.__name__
#         agent_inst.set_methods(func, output_parser)            
#         return agent_inst
#     return decorator