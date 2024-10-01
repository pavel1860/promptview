

import json
import string
import textwrap
from functools import wraps
from typing import (Any, Callable, Coroutine, Generator, Iterable, List,
                    Literal, ParamSpec, Tuple, Type, Union)
from uuid import uuid4

from promptview.llms.messages import (ActionCall, ActionMessage, AIMessage,
                                      BaseMessage)
from promptview.llms.utils.action_manager import Actions
# from promptview.prompt.types import RenderMethodOutput, RenderViewTypes
from promptview.utils.string_utils import convert_camel_to_snake
from pydantic import BaseModel, Field


def view(
    container=None, 
    title: str | None=None,
    actions: List[Type[BaseModel]] | None=None, 
    role: Literal["assistant", "user", "system"]="user",
    name: str | None=None,
    bullet: Literal["number" , "astrix" , "dash" , "none", None] | str=None,
    strip: StripType = None,
    base_model: BaseModelRenderType = 'json',
    base_model_indent: int = 2,
    wrap: ViewWrapperType = None,
    indent: int = 0,
    class_: str | None = None,
    tag: str | None = None,
    ):

    def decorator(func: Callable[P, RenderViewTypes]):
        @wraps(func)
        def wrapper(*args, **kwargs) -> ViewBlock:
            outputs = func(*args, **kwargs)
            if container is not None:
                outputs = container(*outputs if isinstance(outputs, tuple) else (outputs,))
            block_instance = create_view_block(
                views=outputs,
                view_name=func.__name__, 
                name=name, 
                title=title, 
                wrap=wrap, 
                actions=actions, 
                role=role, 
                bullet=bullet,
                strip=strip, 
                base_model=base_model,
                base_model_indent=base_model_indent,
                indent=indent, 
                tag=tag,
                class_=class_
            )   

            return block_instance            
        return wrapper    
    return decorator
