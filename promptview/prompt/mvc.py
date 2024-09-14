
import json
from functools import wraps
import string
import textwrap
from typing import Any, List, Literal, Tuple, Type, Union
from uuid import uuid4

from pydantic import BaseModel, Field
from promptview.utils.string_utils import convert_camel_to_snake
ViewWrapperType = Literal["xml", "markdown", None]
BaseModelRenderType =  Literal['model_dump', 'json']
ListModelRender = Literal['list', 'view_node']

# class ContentBlock(BaseModel):
#     vn_id: str = Field(default_factory=lambda: str(uuid4()), description="id of the view node")
#     name: str = Field(None, description="name of the view function")
#     title: str | None = None
#     numerate: bool = False
#     base_model: BaseModelRenderType = 'json'
#     wrap: ViewWrapperType = None
#     role: Literal["assistant", "user", "system"] | None = "user"
#     role_name: str | None = None
#     # views: List[Union["ViewNode", BaseModel, str]] | Tuple[Union["ViewNode", BaseModel, str]] | "ViewNode" | BaseModel | str 
#     content_blocks: Any
#     index: int | None = None
#     actions: List[BaseModel] | BaseModel | None = None
#     depth: int = 0
#     indent: int | None = None
#     list_model: ListModelRender = 'view_node'
    
#     def get_type(self):
#         return type(self.content_blocks)
    
#     def has_wrap(self):
#         return self.wrap is not None or self.title is not None
    
#     def is_leaf(self):
#         return self.get_type() == str or issubclass(self.get_type(), BaseModel)
    
#     def __hash__(self):
#         return self.vn_id.__hash__()


class ContentBlock(BaseModel):
    uuid: str = Field(default_factory=lambda: str(uuid4()), description="id of the view node")
    name: str | None = Field(None, description="name of the person who created the view")
    view_name: str
    title: str | None = None
    content: str | BaseModel | dict | None = None
    content_blocks: List["ContentBlock"] = []
    role: Literal["assistant", "user", "system"] | None = None
    actions: List[Type[BaseModel]] | Type[BaseModel] | None = None
    
    tag: str | None = None
    class_: str | None = None
    parent_role: Literal["assistant", "user", "system"] | None = None
    numerate: bool = False
    base_model: BaseModelRenderType = 'json'
    wrap: ViewWrapperType = None    
    role_name: str | None = None    
    index: int | None = None
    
    depth: int = 0
    indent: int | None = None
    list_model: ListModelRender = 'view_node'
    
    visited: bool = False
    
    def get_type(self):
        return type(self.content)
        return type(self.content_blocks)
    
    def has_wrap(self):
        return self.wrap is not None or self.title is not None
    
    def is_leaf(self):
        return self.get_type() == str or issubclass(self.get_type(), BaseModel)
    
    def __hash__(self):
        return self.uuid.__hash__()
    
    


def transform_list_to_content_blocks(        
        items: List[Union["ContentBlock", BaseModel, str]],
        view_name: str,
        role: Literal["assistant", "user", "system"] | None = None,
        numerate: bool = False,
        base_model: BaseModelRenderType = 'json',
        indent: int | None = None,
    ):
    """
    ensure that all items in the list are converted to ContentBlock
    """
    sub_views = []
    for i, o in enumerate(items):
        if isinstance(o, str):
            sub_views.append(
                ContentBlock(
                    view_name=f"{view_name}_str_{i}",
                    content=o,
                    numerate=numerate,
                    index=i,
                    role=role,
                    indent=indent,
                    tag=o.tag if hasattr(o, "tag") else None,
                    class_=o.class_ if hasattr(o, "class_") else None
                )   
            )
        elif isinstance(o, dict):
            raise ValueError("dict type not supported")
            sub_views.append(
                ContentBlock(
                    view_name=f"{view_name}_model_{i}",
                    content_blocks=o,
                    numerate=numerate,
                    base_model=base_model,
                    index=i,
                    role=role,
                    indent=indent
                )
            )
        elif isinstance(o, ContentBlock):
            sub_views.append(o)
        elif isinstance(o, BaseModel):
            raise ValueError("dict type not supported")
            sub_views.append(
                ContentBlock(
                    view_name=f"{view_name}_model_{i}",
                    content_blocks=o,
                    numerate=numerate,
                    base_model=base_model,
                    index=i,
                    role=role,
                    indent=indent
                )
            )
        else:
            raise ValueError(f"view type not supported: {type(o)}")
    return sub_views


def create_content_block(
    views,
    view_name: str,
    name: str | None=None,
    title: str | None = None,
    wrap: ViewWrapperType = None,
    actions: List[BaseModel] | BaseModel | None = None,
    role: Literal["assistant", "user", "system"] | None = None,
    numerate: bool = False,
    base_model: BaseModelRenderType = 'json',
    indent: int | None = None,
    tag: str | None = None,
    class_: str | None = None,
):
    content = None
    content_blocks = []
    if type(views) == list or type(views) == tuple:
        content_blocks = transform_list_to_content_blocks(
            views, 
            name, 
            role, 
            numerate, 
            base_model,
        )
    elif isinstance(views, str):
        content = views
    elif isinstance(views, dict):
        content = views
    elif isinstance(views, ContentBlock):
        raise ValueError("ContentBlock type not supported")
    elif isinstance(views, BaseModel):
        content = views
      
    return ContentBlock(
        view_name=view_name,
        name=name,
        title=title,
        content_blocks=content_blocks,
        content=content,
        actions=actions,
        base_model=base_model,
        numerate=numerate,
        wrap=wrap,
        role=role,
        indent=indent,
        tag=tag,
        class_=class_
    )

    
def view(
    container=None, 
    title=None, 
    actions=None, 
    role="user",
    name=None,
    numerate=False,
    base_model: BaseModelRenderType = 'json',
    wrap: ViewWrapperType = None,
    indent: int | None = None,
    class_: str | None = None,
    tag: str | None = None,
    ):

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):                            
            outputs = func(*args, **kwargs)
            if container is not None:
                outputs = container(*outputs if isinstance(outputs, tuple) else (outputs,))
            block_instance = create_content_block(
                views=outputs,
                view_name=func.__name__, 
                name=name, 
                title=title, 
                wrap=wrap, 
                actions=actions, 
                role=role, 
                numerate=numerate, 
                base_model=base_model,
                indent=indent, 
                tag=tag,
                class_=class_
            )   
            # sub_blocks = []
            # if isinstance(outputs, list) or isinstance(outputs, tuple):
            #     sub_blocks = transform_list_to_content_blocks(
            #         outputs, 
            #         name=func.__name__, 
            #         role=role, 
            #         numerate=numerate, 
            #         base_model=base_model,
            #         indent=indent
            #     )
            # else:
            #     sub_blocks = outputs
            # block_instance = ContentBlock(
            #     name=func.__name__,
            #     title=title,
            #     content_blocks=sub_blocks,
            #     actions=actions,
            #     base_model=base_model,
            #     numerate=numerate,
            #     wrap=wrap,
            #     role=role,
            #     role_name=name,
            #     indent=indent,
            # )
            return block_instance            
        return wrapper    
    return decorator

def list_view(rules: list[str], numbered: bool = True):
    if numbered:
        return "\n".join([f"{i}. {r}" for i, r in enumerate(rules)])
    else:
        return "\n".join(rules)



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
    return "\t" * num

def add_tabs(content: str, tabs: int):
    return "\n".join([render_tabs(tabs) + c for c in content.split("\n")])
    # return content.replace("\n", f"\n{render_tabs(tabs)}")


def render_model(block: ContentBlock):
    model = block.content_blocks
    prompt = ""
    if block.numerate and block.index:
        prompt += f"{block.index + 1}. "
        
    if block.base_model == 'json':
        return add_tabs(prompt + json.dumps(model.model_dump(), indent=block.indent), block.depth)
    elif block.base_model == 'model_dump':
        return add_tabs(prompt + str(model.model_dump()) + "\n", block.depth)
    else:
        raise ValueError(f"base_model type not supported: {block.base_model}")


def render_string(block: ContentBlock, **kwargs):
    prompt = ''
    depth = block.depth + 1 if block.has_wrap() else block.depth
    if block.numerate and block.index:
        prompt += f"{block.index + 1}. "    
    prompt += textwrap.dedent(block.content_blocks).strip()
    prompt = add_tabs(prompt, depth)
    return replace_placeholders(prompt, **kwargs)

def render_dict(block: ContentBlock):
    prompt = ''
    depth = block.depth + 1 if block.has_wrap() else block.depth
    if block.numerate and block.index:
        prompt += f"{block.index + 1}. "
    prompt += json.dumps(block.content_blocks, indent=block.indent)
    return add_tabs(prompt, depth)

def add_wrapper(content: str, block: ContentBlock):
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


    
def render_wrapper_starting(block: ContentBlock):
    title = block.title if block.title is not None else ''
    if block.wrap == "xml":
        return add_tabs(f"<{title}>", block.depth)
    elif block.wrap == "markdown":
        return add_tabs(f"## {title}", block.depth)
    return add_tabs(f'{title}:', block.depth)

def render_wrapper_ending(block: ContentBlock):
    title = block.title if block.title is not None else ''
    if block.wrap == "xml":
        return add_tabs(f"</{title}>", block.depth)
    return ''



def validate_node(block: any):
    if type(block) == str:
        return ContentBlock(content_blocks=block)    
    return block



def get_action_name(action_class: Type[BaseModel]):
    if hasattr(action_class, "_title"):
        return action_class._title.default
    return convert_camel_to_snake(action_class.__name__)


def find_action(action_name, actions):
    for action in actions:
        if get_action_name(action) == action_name:
            return action
    return None





#? in render view we are using 2 stacks so that we can render the views in the correct order
# ?is a view is between 2 strings, we want to render the view between the strings
def render_block(block: ContentBlock | tuple, **kwargs):

    if type(block) == tuple:
        stack = [*reversed(block)]    
    else:
        stack = [block]

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
                for block in reversed(peek_block.content_blocks):
                    if peek_block.has_wrap():
                        block.depth = peek_block.depth + 1
                    else:
                        block.depth = peek_block.depth
                    
                    stack.append(block)
            elif issubclass(peek_block.get_type(), ContentBlock):
                if peek_block.has_wrap():
                    peek_block.content_blocks.depth = peek_block.depth + 1
                stack.append(peek_block.content_blocks)
            elif issubclass(peek_block.get_type(), BaseModel):
                base_models[peek_block.content_blocks.__class__.__name__] = peek_block.content_blocks
                result.append(render_model(peek_block))
            else:
                raise ValueError(f"block type not supported: {type(peek_block)}")
        else:
            if peek_block.has_wrap():
                result.append(render_wrapper_ending(peek_block))
            stack.pop(-1)
    prompt = "\n".join(result)
    return prompt, result, base_models