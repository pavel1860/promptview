from __future__ import annotations

import json
import string
import textwrap
from functools import wraps
from typing import (Any, Callable, Coroutine, Generator, Iterable, List,
                    Literal, ParamSpec, Sequence, Tuple, Type, Union)
from uuid import uuid4


from promptview.prompt.view_block import ViewBlock
from promptview.utils.string_utils import convert_camel_to_snake
from pydantic import BaseModel, Field







class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            if key not in kwargs:
                raise KeyError(f"Missing value for key: '{key}'")
            return kwargs[key]
        else:
            return super().get_value(key, args, kwargs)
        
def replace_placeholders(template: str, **kwargs) -> str:
    formatter = SafeFormatter()
    formatted_string = formatter.format(template, **kwargs)
    return formatted_string


def render_tabs(num: int):
    # return "\t" * num
    return "  " * num

def add_tabs(content: str, tabs: int):
    return "\n".join([render_tabs(tabs) + c for c in content.split("\n")])
    # return content.replace("\n", f"\n{render_tabs(tabs)}")


def render_model(block: ViewBlock):
    model = block.view_blocks
    if type(model) == list:
        raise ValueError("base model cannot be a list for rendering")
    prompt = ""
    if block.bullet and block.index:
        prompt += f"{block.index + 1}. "
        
    if block.base_model == 'json':
        return add_tabs(prompt + json.dumps(model.model_dump(), indent=block.base_model_indent), block.depth)
    elif block.base_model == 'model_dump':
        return add_tabs(prompt + str(model.model_dump()) + "\n", block.depth)
    else:
        raise ValueError(f"base_model type not supported: {block.base_model}")


def render_string(block: ViewBlock, **kwargs):
    prompt = ''
    if type(block.view_blocks) != str:
        raise ValueError("view block content must be a string for string rendering")
    depth = block.depth + 1 if block.has_wrap() else block.depth
    if block.bullet and block.index:
        prompt += f"{block.index + 1}. "    
    prompt += textwrap.dedent(block.view_blocks).strip()
    prompt = add_tabs(prompt, depth)
    return replace_placeholders(prompt, **kwargs)

def render_dict(block: ViewBlock):
    prompt = ''
    depth = block.depth + 1 if block.has_wrap() else block.depth
    if block.bullet and block.index:
        prompt += f"{block.index + 1}. "
    prompt += json.dumps(block.view_blocks, indent=block.base_model_indent)
    return add_tabs(prompt, depth)

def add_wrapper(content: str, block: ViewBlock):
    title = block.title if block.title is not None else ''
    if block.wrap == "xml":
        return add_tabs((
            f"<{title}>\n"
            f"\n{content}"
            f"</{title}>\n"   
        ), block.depth)
    
    if block.wrap == "markdown":
        return add_tabs((
            f"## {title}\n"
            f"\t{content}\n"
        ), block.depth)
    return add_tabs((
        f"{title}:"
        f"\t{content}"
        ), block.depth)


    
def render_wrapper_starting(block: ViewBlock):
    title = block.title if block.title is not None else ''
    if block.wrap == "xml":
        return add_tabs(f"<{title}>", block.depth)
    elif block.wrap == "markdown":
        return add_tabs(f"## {title}", block.depth)
    return add_tabs(f'{title}:', block.depth)

def render_wrapper_ending(block: ViewBlock):
    title = block.title if block.title is not None else ''
    if block.wrap == "xml":
        return add_tabs(f"</{title}>", block.depth)
    return ''





def get_action_name(action_class: Type[BaseModel]):
    if hasattr(action_class, "_title"):
        return action_class._title.default # type: ignore
    return convert_camel_to_snake(action_class.__name__)


def find_action(action_name, actions):
    for action in actions:
        if get_action_name(action) == action_name:
            return action
    return None





#? in render view we are using 2 stacks so that we can render the views in the correct order
# ?is a view is between 2 strings, we want to render the view between the strings
def render_block(block: ViewBlock | tuple, **kwargs):

    if type(block) == tuple:
        stack: List[ViewBlock] = [*reversed(block)]    
    else:
        stack: List[ViewBlock] = [block]

    base_models = {}
    visited = set()
    result = []
    while stack:
        # peek_node = validate_node(stack[-1])
        peek_block = stack[-1]
                            
        if peek_block not in visited:
            visited.add(peek_block)
            if peek_block.has_wrap():
                result.append(render_wrapper_starting(peek_block))
            if peek_block.get_type() == str:
                result.append(render_string(peek_block, **kwargs))
            elif peek_block.get_type() == dict:
                result.append(render_dict(peek_block))
            elif peek_block.get_type() == list or peek_block.get_type() == tuple:
                for block in reversed(peek_block.view_blocks):
                    if peek_block.has_wrap():
                        block.depth = peek_block.depth + 1
                    else:
                        block.depth = peek_block.depth
                    
                    stack.append(block)
            elif issubclass(peek_block.get_type(), ViewBlock):
                if peek_block.has_wrap():
                    peek_block.view_blocks.depth = peek_block.depth + 1
                stack.append(peek_block.view_blocks)
            elif issubclass(peek_block.get_type(), BaseModel):
                base_models[peek_block.view_blocks.__class__.__name__] = peek_block.view_blocks
                result.append(render_model(peek_block))
            else:
                raise ValueError(f"block type not supported: {type(peek_block)}")
        else:
            if peek_block.has_wrap():
                result.append(render_wrapper_ending(peek_block))
            stack.pop(-1)
    prompt = "\n".join(result)
    return prompt, result, base_models