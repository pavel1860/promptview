
import asyncio
import inspect
import json
from functools import wraps
from typing import (Any, Awaitable, Callable, Dict, Generator, List, Literal,
                    Optional, Tuple, Type, Union, get_args)

from promptview.llms.context import Context
from promptview.llms.messages import (AIMessage, )
from promptview.utils.function_utils import call_function
from promptview.llms.llm import AzureOpenAiLLM, OpenAiLLM
from promptview.prompt.chat_prompt import ChatPrompt
from pydantic import BaseModel, Field




def prompt(
    model: str = "gpt-3.5-turbo-0125",
    llm: Union[OpenAiLLM, AzureOpenAiLLM, None] = None,
    system_prompt: Optional[str] = None,
    background: Optional[str] = None,
    task: Optional[str] = None,
    rules: Optional[str | List[str] | Callable] = None,
    examples: Optional[str | List[str] | Callable] = None,
    actions: Optional[List[Type[BaseModel]]] = None,
    response_model: Optional[Type[BaseModel]] = None,
    parallel_actions: bool = True,
    is_traceable: bool = True,
    output_parser: Optional[Callable] = None,
    tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,    
):
    if llm is None:
        llm = OpenAiLLM(
            model=model, 
            parallel_tool_calls=parallel_actions
        )
    def decorator(func) -> Callable[..., Awaitable[AIMessage]]:
        
        @wraps(func)
        async def wrapper(**kwargs) -> AIMessage:
            prompt = ChatPrompt(
                name=func.__name__,
                model=model,
                llm=llm,
                system_prompt=system_prompt,
                background=background,
                task=task,
                rules=rules,
                examples=examples,
                actions=actions,
                response_model=response_model,
                tool_choice=tool_choice,
            )
            prompt.set_methods(func, output_parser)
            return await prompt(**kwargs)

        return wrapper
    
    return decorator
