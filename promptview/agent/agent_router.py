
from functools import wraps
from typing import Dict, List, Optional, Type, Union
from pydantic import BaseModel
from promptview.state.context import Context
from promptview.llms.messages import ActionMessage, HumanMessage
from promptview.utils.function_utils import call_function, filter_func_args
from promptview.prompt.chat_prompt import ChatPrompt
from promptview.llms.tracer import Tracer
import inspect
from promptview.prompt.decorator import prompt


class AgentRouter(BaseModel):
    name: str
    model: str = "gpt-4o"    
    iterations: int = 1
    router_prompt: Type[ChatPrompt] | None = None
    add_input_history: bool = False    

    _action_handlers: Dict[str, callable] = {}

    def handle(self, action: BaseModel, handler: callable):
        self._action_handlers[action.__name__] =  handler

    
    async def __call__(self, context: Context, message: str, iterations: int | None = None, tracer_run=None, **kwargs):
        iterations = iterations or self.iterations

        # context.history.add(HumanMessage(content=message))
        has_action_response = False
        with Tracer(
            name=self.name,
            inputs={"message": message} | kwargs,
            tracer_run=tracer_run
        ) as tracer_run:
            
            if self.add_input_history:
                context.history.add(context, HumanMessage(content=message), str(tracer_run.id), "user")
            action_output = None
            for i in range(iterations):
                # response = await self.router_prompt(context=context, message=message, tracer_run=tracer_run, **kwargs)                
                response = await call_function(self.router_prompt.__call__, context=context, message=message, tracer_run=tracer_run, action_output=action_output, **kwargs)
                context.history.add(context, response, str(tracer_run.id), self.name)
                if response.content:
                    yield response
                    # print(response.content)
                if response.actions:
                    for i, action in enumerate(response.actions):
                        action_handler = self._action_handlers[action.__class__.__name__]
                        if inspect.isasyncgenfunction(action_handler):
                            gen_kwargs = filter_func_args(action_handler, {"context": context, "action": action, "message": message, "tracer_run": tracer_run} | kwargs)                            
                            async for output in action_handler(**gen_kwargs):
                                if output is None:
                                    break
                                yield output
                        elif inspect.isfunction(action_handler):
                            action_output = await call_function(action_handler, context=context, action=action, message=message, tracer_run=tracer_run, **kwargs)                                                                       
                        else:
                            raise ValueError(f"Invalid action handler: {action_handler}")
                        if action_output:
                            has_action_response = True
                            
                            if type(action_output) == str:
                                action_output_str = action_output
                            elif isinstance(action_output, BaseModel):
                                action_output_str = action_output.model_dump_json()
                            else:
                                raise ValueError(f"Invalid action output: {action_output}")
                            tool_response = ActionMessage(
                                    content=action_output_str,
                                    tool_call=response.tool_calls[i]
                                )
                            response.add_tool_response(tool_response)
                            context.history.add(context, tool_response, str(tracer_run.id), self.name) 
                else:
                    break
                    
                if not has_action_response:
                    break
                message = None                  
            tracer_run.end(outputs={"status": "success"})


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


    def reducer(self, action: BaseModel):
        def decorator(func):
            self.handle(action, func)
            return func
        return decorator
    
    
    
AgentRouter.prompt = prompt