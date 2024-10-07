
import inspect
from abc import abstractmethod
from functools import wraps
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, List,
                    Literal, Optional, ParamSpec, Type, TypeVar, Union)

from promptview.agent.handlers import (BaseActionHandler, FunctionHandler,
                                       PromptHandler)
from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.llm2 import LLM
from promptview.llms.messages import (ActionCall, ActionMessage, AIMessage,
                                      HumanMessage, MessageChunk)
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracer import Tracer
from promptview.prompt.base_prompt import Prompt, PromptChunk
from promptview.prompt.chat_prompt import ChatPrompt
from promptview.prompt.decorator import prompt
from promptview.prompt.execution_context import ExecutionContext, ExLifecycle
from promptview.prompt.mvc import RenderMethodOutput
from promptview.prompt.types import ToolChoiceParam
from promptview.state.context import Context
from promptview.utils.function_utils import call_function, filter_func_args
from pydantic import BaseModel, Field

P = ParamSpec("P")
R = TypeVar("R")  

# class Agent(Prompt[P], Generic[P]):
class Agent(ChatPrompt[P], Generic[P]):
    iterations: int = 1
    add_input_history: bool = False 
    is_router: bool = False
    _action_handlers: Dict[str, BaseActionHandler] = {}

    def handle(self, action: Type[BaseModel], handler: BaseActionHandler):   
        self._action_handlers[action.__name__] =  handler
        if self.actions is None:
            self.actions = [action]
        else:
            existing_action = [a for a in self.actions if a == action]
            if existing_action:
                raise ValueError(f"Action {action} already exists in actions list")
            self.actions.append(action)
            
        
    
    def get_action_handler(self, action_call: ActionCall) -> BaseActionHandler:
        handler = self._action_handlers[action_call.action.__class__.__name__]
        if not handler:
            raise ValueError(f"Action handler not found for {action_call.action.__class__.__name__}")
        return handler
    
    
    def build_execution_context(
            self,
            ex_ctx: ExecutionContext | None = None,
            *args: Any,
            **kwargs: Any
            # *args: P.args,
            # **kwargs: P.kwargs
        ) -> ExecutionContext:
        if ex_ctx is not None:
            return ex_ctx
            # return ex_ctx.create_child(
            #     prompt_name=self._view_builder.prompt_name,
            #     ex_type="agent",
            #     kwargs=kwargs,
            # )
        return ExecutionContext(
            prompt_name=self._view_builder.prompt_name,
            is_traceable=self.is_traceable,
            context=kwargs.pop("context", None),
            ex_type="agent",
            run_type="chain",
            kwargs=kwargs
        )
    
    
    def process_action_output(self, ex_ctx: ExecutionContext ,action_call: ActionCall, action_output)-> ExecutionContext:
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
        
    
    
    
    
    async def call_agent_prompt(self, ex_ctx: ExecutionContext, is_router: bool=False) -> ExecutionContext:
        handler_kwargs = filter_func_args(self._render_method, ex_ctx.kwargs)
        prompt_ctx = ex_ctx.create_child(
            prompt_name=self._view_builder.prompt_name,
            ex_type="agent",
            run_type="prompt",
            kwargs=handler_kwargs,
        )
        prompt_ctx = await call_function(
                self.call_ctx,
                ex_ctx=prompt_ctx,
                **handler_kwargs
            ) 
        ex_ctx.merge_child(prompt_ctx)
        return ex_ctx
    
    
    
    async def __call__(
        self,
        ex_ctx: ExecutionContext | None = None,
        *args: P.args, 
        **kwargs: P.kwargs
    ) -> AsyncGenerator[AIMessage, None]:
        agent_ctx = self.build_execution_context(ex_ctx=ex_ctx, *args, **kwargs)
        with agent_ctx.start_execution(
            prompt_name=self._view_builder.prompt_name,
            kwargs=kwargs,
        ) as agent_ctx:    
            try:
                for i in range(self.iterations):
                    agent_ctx = await self.call_agent_prompt(agent_ctx)
                    if agent_ctx.lifecycle_phase == ExLifecycle.SEND_MESSAGE:
                        yield agent_ctx.send_message()
                    if agent_ctx.lifecycle_phase == ExLifecycle.ACTION_CALLS:
                        for action_call in agent_ctx.action_calls:
                            action_handler = self.get_action_handler(action_call)                        
                            if action_handler.type == "async_generator":
                                stream_gen = action_handler.stream(action_call, ex_ctx=agent_ctx) #type: ignore
                                async for output in stream_gen:
                                    if output is None:
                                        break
                                    yield output
                            elif action_handler.type == "function":
                                agent_ctx = await action_handler.call(action_call, agent_ctx)
                            elif action_handler.type == "prompt":
                                agent_ctx = await action_handler.call(action_call, agent_ctx)
                            else:
                                raise ValueError(f"Invalid action handler type: {action_handler.type}")                                            
                            if agent_ctx.lifecycle_phase == ExLifecycle.SEND_MESSAGE:
                                yield agent_ctx.send_message()
                            agent_ctx.finish_action_call(action_call)
                            
                    elif agent_ctx.lifecycle_phase == ExLifecycle.FINISHED:
                        return
                    else:
                        raise ValueError(f"Invalid lifecycle phase: {agent_ctx.lifecycle_phase}")
                            
            except Exception as e:
                raise e
            finally:
                # agent_ctx.add_response(AIMessage(content="End of execution"))
                agent_ctx.end_execution("End of execution")
                print("End of execution")
            # ex_ctx.end_execution()
            
            
    async def stream(
        self,
        ex_ctx: ExecutionContext | None = None,
        *args: P.args, 
        **kwargs: P.kwargs
    )-> AsyncGenerator[PromptChunk, None]:
        agent_ctx = self.build_execution_context(ex_ctx=ex_ctx, *args, **kwargs)
        try:
            for i in range(self.iterations):
                agent_ctx = await self.call_agent_prompt(agent_ctx)
                # if agent_ctx.lifecycle_phase == ExLifecycle.SEND_MESSAGE:
                #     yield agent_ctx.send_message()
                if agent_ctx.lifecycle_phase == ExLifecycle.ACTION_CALLS:
                    for action_call in agent_ctx.action_calls:
                        action_handler = self.get_action_handler(action_call)                        
                        if action_handler.type == "async_generator":
                            stream_gen = action_handler.stream(action_call, ex_ctx=agent_ctx) #type: ignore
                            async for output in stream_gen:
                                if output is None:
                                    break
                                yield output
                        elif action_handler.type == "function":
                            agent_ctx = await action_handler.call(action_call, agent_ctx)
                        elif action_handler.type == "prompt":
                            async for msg in action_handler.stream(action_call, agent_ctx):
                                if not msg.did_finish:
                                    yield msg
                                else:
                                    if not msg.ex_ctx:
                                        raise ValueError(f"Invalid execution context: {msg.ex_ctx}")
                                    agent_ctx = msg.ex_ctx
                                    yield msg
                        else:
                            raise ValueError(f"Invalid action handler type: {action_handler.type}")                                            
                        # if agent_ctx.lifecycle_phase == ExLifecycle.SEND_MESSAGE:
                            # yield agent_ctx.send_message()
                        agent_ctx.finish_action_call(action_call)
                        
                elif agent_ctx.lifecycle_phase == ExLifecycle.FINISHED:
                    return
                else:
                    raise ValueError(f"Invalid lifecycle phase: {agent_ctx.lifecycle_phase}")
                        
        except Exception as e:
            raise e
        finally:
            agent_ctx.add_response(AIMessage(content="End of execution"))
            print("End of execution")
            


    def route(self, action: Type[BaseModel], prompt: Prompt, stream: bool = False):        
        self.handle(action, PromptHandler(action=action, is_routing=True, prompt=prompt))

    def reducer(self, action: Type[BaseModel]):
        def decorator(func):            
            self.handle(action, FunctionHandler(action=action, handler=func))
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
) -> Callable[[Callable[T, RenderMethodOutput]], Agent[T]]:
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
                tool_choice=tool_choice or Agent.get_default_field("tool_choice"),
                actions=actions,
                is_traceable=is_traceable,
                iterations=iterations,
                **kwargs
            )
        agent_ins._name=func.__name__
        agent_ins.set_methods(func, output_parser)            
        return agent_ins        
    return decorator
