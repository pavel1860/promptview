from functools import wraps
from typing import (Any, Awaitable, Callable, List, Literal, Optional,
                    ParamSpec, Tuple, Type, TypeVar)

from promptview.llms import OpenAiLLM
from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.llm import LLM
from promptview.llms.messages import AIMessage
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.chat_prompt import ChatPrompt
from promptview.prompt.types import RenderMethodOutput, ToolChoiceParam
from pydantic import BaseModel, Field

# T = TypeVar('T')

# def prompt( 
#     self=None,   
#     model: str = "gpt-3.5-turbo-0125",
#     llm: LLM | None = None,
#     system_prompt: Optional[str] = None,
#     background: Optional[str] = None,
#     task: Optional[str] = None,
#     rules: Optional[str | List[str] | Callable] = None,
#     examples: Optional[str | List[str] | Callable] = None,
#     actions: Optional[List[Type[BaseModel]]] = None,
#     response_model: Optional[Type[BaseModel]] = None,
#     parallel_actions: bool = True,
#     is_traceable: bool = True,
#     output_parser: Callable[[AIMessage], T] | None = None,
#     tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,
# ):
#     if llm is None:
#         llm = OpenAiLLM(
#             model=model, 
#             parallel_tool_calls=parallel_actions
#         )
#     def decorator(func) -> Callable[..., Awaitable[T]]:
#         prompt = ChatPrompt[T](
#                 name=func.__name__,
#                 model=model,
#                 llm=llm,
#                 system_prompt=system_prompt,
#                 background=background,
#                 task=task,
#                 rules=rules,
#                 examples=examples,
#                 actions=actions,
#                 response_model=response_model,
#                 tool_choice=tool_choice,
#             )
#         prompt.set_methods(func, output_parser)
#         if self:
#             self.router_prompt = prompt
#         @wraps(func)
#         async def wrapper(**kwargs) -> T:            
#             return await prompt(**kwargs)

#         return wrapper
    
#     return decorator

# from promptview.prompt.chat_prompt import ChatPrompt

# prompt = ChatPrompt.decorator_factory()



P = ParamSpec("P")
R = TypeVar("R")  

def decorator_factory(cls: Type[Prompt[P]]):
    def prompt_decorator( 
        self=None,   
        model: str = "gpt-4o",
        llm: LLM | None = None,            
        parallel_actions: bool = True,
        is_traceable: bool = True,
        output_parser: Callable[[AIMessage], R] | None = None,
        tool_choice: ToolChoiceParam = None,
        actions: List[Type[BaseModel]] | None = None,
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
        def decorator(func: Callable[P, RenderMethodOutput]) -> Prompt[P]:
            prompt = cls[P](
                    model=model, #type: ignore
                    llm=llm,                        
                    tool_choice=tool_choice or cls.model_fields.get("tool_choice").default,
                    actions=actions,
                    is_traceable=is_traceable,
                    **kwargs
                )
            prompt._name=func.__name__
            prompt.set_methods(func, output_parser)            
            return prompt        
        return decorator
    
    return prompt_decorator




prompt = decorator_factory(ChatPrompt)