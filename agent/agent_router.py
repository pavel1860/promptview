
import inspect
from functools import wraps
from typing import (Callable, Dict, Generic, List, Literal, Optional,
                    ParamSpec, Type, TypeVar, Union)

from promptview.llms.interpreter.messages import (ActionCall, ActionMessage, AIMessage,
                                      HumanMessage)
from promptview.llms.tracer import Tracer
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.chat_prompt import ChatPrompt
from promptview.prompt.decorator import prompt
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
        
    

    
P = ParamSpec("P")
class AgentRouter(BaseModel, Generic[P]):
    name: str
    model: str = "gpt-4o"    
    iterations: int = 1
    router_prompt: Type[ChatPrompt] | None = None
    add_input_history: bool = False 
    is_traceable: bool = True 
    is_router: bool = False
    # prompt: Callable = Field(default_factory=prompt)
    prompt = prompt

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
    
    
    def process_action_output(self, action_call: ActionCall, action_output)-> ActionMessage:
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
        return message
        
    def route(self, action: Type[BaseModel], prompt: Prompt, stream: bool = False):
        self.handle(action, prompt, is_stream=stream)

    
    async def __call__(self, context: Context, message: HumanMessage | str, iterations: int | None = None, tracer_run=None, **kwargs):
        iterations = iterations or self.iterations
        if not isinstance(message, HumanMessage) and isinstance(message, str):
            message = HumanMessage(content=message)
        else:
            raise ValueError("Invalid message type")
        
        if self.router_prompt is None:
            raise ValueError("Router prompt is not set")
        with Tracer(
            name=self.name,
            is_traceable=self.is_traceable,
            inputs={"message": message.content} | kwargs,
            session_id=context.session_id,
            tracer_run=tracer_run
        ) as tracer_run:
            
            action_output = None
            for i in range(iterations):           
                response = await call_function(
                        self.router_prompt.__call__, 
                        context=context, 
                        message=message, 
                        tracer_run=tracer_run, 
                        action_output=action_output, 
                        **kwargs
                    )
                if not self.is_router:
                    context.history.add(context, message, str(tracer_run.id), "user")
                    context.history.add(context, response, str(tracer_run.id), self.name)                
                if response.content:
                    tracer_run.add_outputs(response)
                    yield response
                if response.action_calls:
                    for action_call in response.action_calls:
                        action_handler = self.get_action_handler(action_call)
                        if action_handler.type == "async_generator":
                            gen_kwargs = filter_func_args(action_handler, {"context": context, "action": action_call.action, "message": message.content, "tracer_run": tracer_run} | kwargs)
                            target = action_handler.handler.stream if not action_handler.is_prompt else action_handler.handler 
                            async for output in target(**gen_kwargs):
                                if output is None:
                                    break
                                tracer_run.add_outputs(output)
                                yield output
                        elif action_handler.type == "function":
                            target = action_handler.handler.__call__ if not action_handler.is_prompt else action_handler.handler
                            action_output = await call_function(target, context=context, action=action_call.action, message=message.content, tracer_run=tracer_run, **kwargs)
                        else:
                            raise ValueError(f"Invalid action handler type: {action_handler.type}")
                        # if inspect.isasyncgenfunction(action_handler):
                        #     gen_kwargs = filter_func_args(action_handler, {"context": context, "action": action_call.action, "message": message.content, "tracer_run": tracer_run} | kwargs)
                        #     async for output in action_handler(**gen_kwargs):
                        #         if output is None:
                        #             break
                        #         tracer_run.add_outputs(output)
                        #         yield output
                        # elif inspect.isfunction(action_handler):
                        #     action_output = await call_function(action_handler, context=context, action=action_call.action, message=message.content, tracer_run=tracer_run, **kwargs)
                        # elif isinstance(action_handler, Prompt):
                        #     action_output = await call_function(action_handler.__call__, context=context, message=message, tracer_run=tracer_run, **kwargs)
                        # else:
                        #     raise ValueError(f"Invalid action handler: {action_handler}")
                        if action_output:
                            if isinstance(action_output, AIMessage):
                                tracer_run.add_outputs(response)
                                yield action_output
                            else:
                                message = self.process_action_output(action_call, action_output)                            
                        else:
                            return
                else:
                    break                    
            else:
                context.history.add(context, message, str(tracer_run.id), "user")
                


    # def prompt(
    #     self,
    #     model: str = "gpt-3.5-turbo-0125",
    #     llm: Union[OpenAiLLM, AzureOpenAiLLM, None] = None,
    #     background: Optional[str] = None,
    #     task: Optional[str] = None,
    #     rules: Optional[str | List[str]] = None,
    #     examples: Optional[str | List[str]] = None,
    #     actions: Optional[List[Type[BaseModel]]] = None,
    #     response_model: Optional[Type[BaseModel]] = None,
    #     parallel_actions: bool = False,
    #     is_traceable: bool = True
    # ):
    #     if llm is None:
    #         llm = OpenAiLLM(
    #             model=model,
    #             parallel_tool_calls=parallel_actions
    #         )
        
    #     def decorator(func):            
    #         prompt = ChatPrompt(
    #                 name=func.__name__,
    #                 model=model,
    #                 llm=llm,
    #                 background=background,
    #                 task=task,
    #                 rules=rules,
    #                 examples=examples,
    #                 actions=actions,
    #                 response_model=response_model,
    #             )
    #         prompt.set_render_method(func)
    #         self.router_prompt = prompt
    #         @wraps(func)
    #         async def wrapper(**kwargs):             
    #             return await prompt(**kwargs)                
                
    #         return wrapper
        
    #     return decorator


    def reducer(self, action: Type[BaseModel]):
        def decorator(func):
            self.handle(action, func)
            return func
        return decorator
    
    
# setattr(AgentRouter, "prompt", prompt)  
# AgentRouter.prompt = prompt