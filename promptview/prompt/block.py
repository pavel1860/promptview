from abc import abstractmethod
from functools import wraps
from uuid import uuid4
from pydantic import BaseModel, Field
from typing import Callable, Generic, Literal, ParamSpec, TypeVar
import json
from typing import Protocol, runtime_checkable

from promptview.utils.string_utils import int_to_roman


BulletType = Literal["number", "alpha", "roman", "roman_lower", "*", "-"]
TitleType = Literal["xml", "md", "html"]

class Style(BaseModel):
    bclass: str | None = Field(default=None, description="The class for the block")
    ttype: TitleType  | None = Field(default=None, description="The style of the title")
    bullet: BulletType | None = Field(default=None, description="The bullet style for the list")
    prefix: str | None = Field(default=None, description="prefix to add to the block title")
    postfix: str | None = Field(default=None, description="postfix to add to the block title")
    tabs: int = Field(default=0, description="number of tabs to add to the block content")
    indent: int = Field(default=0, description="number of spaces to indent the block content")
    dropout: float = Field(default=0.0, description="dropout probability for the block")
    
    def copy_tabs(self, eq: int | None = None, inc: int | None = None, dec: int | None = None):
        if eq is not None:
            return self.model_copy(update={"tabs": eq})
        elif inc is not None:
            return self.model_copy(update={"tabs": self.tabs + inc})
        elif dec is not None:
            return self.model_copy(update={"tabs": self.tabs - dec})
        else:
            raise ValueError("Must provide one of eq, inc, or dec")
        
    def copy_prefix(self, prefix: str):
        return self.model_copy(update={"prefix": prefix})
    
    def copy_postfix(self, postfix: str):
        return self.model_copy(update={"postfix": postfix})


class StyleManager():
    
    def __init__(self, styles: dict):
        self.styles = styles
        
    def get(self, block_id, style: Style | None = None):
        style_dict = self.styles.get(block_id, None)
        if style_dict is None:
            return style
        if style is None:
            return Style(**style_dict)
        return Style(**(style_dict | style.model_dump()))
    
    def add(self, style_dict: dict):
        self.styles.update(style_dict)
    
    def get_style(self, block: "BaseBlock", style: Style | None = None):
        style = block.get_style(style=self.get(block.id, style))
        return style
    
    
style_manager = StyleManager({})



@runtime_checkable
class Renderable(Protocol):
    
    def render(self, style: Style)->str:
        """
        Classes conforming to the Renderable Protocol must implement
        a `render` method with the specified arguments.
        """
        ...
        

def tabs_str(style: Style):
    return "  " * style.tabs
       

class strblk(str, Renderable):
    
    def render(self, style: Style):
        content = self
        if style.prefix:
            content = style.prefix + content
        if style.postfix:
            content = content + style.postfix
        if style.tabs or style.indent:
            content = "  " * (style.tabs or style.indent) + content
        return content
    
    
class dictblk(dict, Renderable):
    
    def render(self, style: Style):
        content = json.dumps(self, indent=style.indent)
        return content

   
# class listblk(list):
    
#     def render(self, indent=4):
#         return json.dumps(self, indent=indent)



class BaseBlock(BaseModel):
    uuid: str = Field(default_factory=lambda: str(uuid4()))
    id: str | None = Field(default=None, description="The id for the block")
    tag: str | None = Field(default=None, description="The tag for the block")
    bclass: str = Field(default="block", description="The class for the block")
    # style: Style = Field(default_factory=lambda: Style())
    _items: list[Renderable] = []
    
    # class Config:
    #     arbitrary_types_allowed = True
    
    def append(self, item):        
        if not isinstance(item, Renderable):
            if isinstance(item, str):
                item = strblk(item)
            elif isinstance(item, dict):
                item = dictblk(item)                
            else:
                raise ValueError(f"Invalid item type: {type(item)}. Must be str, dict, or Renderable")
        self._items.append(item)
        return item
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
    def __call__(self, *args):
        for arg in args:
            self.append(arg)
        return self
    
    def __add__(self, other):
        self.append(other)
        return self
    
    @abstractmethod
    def get_style(self, style: Style | None = None) -> Style:
        """
        generates a style object for the block
        """
        ...
        # if style is not None:
        #     return style.model_copy(update=self.style.model_dump())
        # return self.style
    
    def render(self, style: Style | None = None):        
        new_style = self.get_style(style)
        # new_style.tabs += 1
        return "\n".join([item.render(style=new_style) for item in self._items])
    
    def __repr__(self) -> str:
        repr_str = super().__repr__()
        return repr_str + "\n" + self.render()
    
    
class TitleBlock(BaseBlock):
    ttype: TitleType = Field(default="md", description="The style of the title")
    title: str | None = Field(default=None, description="The title of the block")
    
    def _render_md(self):
        content = super().render()
        return f"## {self.title}\n{content}"
    
    def _render_html(self):
        content = super().render()
        return f"<h2>{self.title}</h2>\n{content}"
    
    def _render_xml(self):
        content = super().render()
        return f"<${self.title}>\n{content}\n</{self.title}>"    
    
    def get_style(self, style: Style | None = None) -> Style:        
        curr_style = Style(ttype=self.ttype)
        if style is not None:
            curr_style = curr_style.model_copy(update=style.model_dump())
        return curr_style
    
    def _render_title(self, content: str, style: Style):
        if style.ttype == "md":
            content = f"{tabs_str(style)}## {self.title}\n{content}"
        elif style.ttype == "html":
            content = f"{tabs_str(style)}<h2>{self.title}</h2>\n{content}"
        elif style.ttype == "xml":
            content = f"{tabs_str(style)}<{self.title}>\n{content}\n</{self.title}>"
        else:
            raise ValueError(f"Invalid title style: {style.ttype}")
        return content

    def render(self, style: Style | None = None):
        # style = self.get_style(style)
        style = style_manager.get_style(self, style)        
        if self.title:
            content = super().render(style=style.copy_tabs(inc=1))
            content = self._render_title(content, style)        
        else:
            content = super().render(style=style)
        return content
    
    
    def list(self, title=None, ttype: TitleType="md", bullet: BulletType = "-", id: str | None = None):        
        lb = ListBlock(title=title, ttype=ttype, bullet=bullet, id=id)
        self.append(lb)
        return lb
    
    
# class Block(TitleBlock):
#     ...
    
    
    
class ListBlock(TitleBlock):
    bullet: BulletType = Field(default="-", description="The bullet style for the list")

    
    def _get_prefix(self, idx: int):
        if self.bullet == "number":
            return f"{idx+1}. "
        elif self.bullet == "alpha":
            return f"{chr(97+idx)}. "
        elif self.bullet == "roman":
            return int_to_roman(idx+1) + ". "
        elif self.bullet == "roman_lower":
            return int_to_roman(idx+1, upper=False) + ". "
        return f"{self.bullet} "
    
    def _get_list_item(self, idx, item):
        bullet = self._get_prefix(idx)
        return f"{bullet} {item}"
    
    def get_style(self, style: Style | None = None) -> Style:        
        curr_style = Style(bullet=self.bullet, ttype=self.ttype)
        if style is not None:
            curr_style = curr_style.model_copy(update=style.model_dump())
        return curr_style
    
    def render(self, style: Style | None = None):
        new_style = style_manager.get_style(self, style)
        new_style.tabs += 1
        content = "\n".join([item.render(style=new_style.model_copy(update={"prefix": self._get_prefix(idx)})) for idx, item in enumerate(self._items)])
        if self.title:
            content = self._render_title(content, new_style)                    
        return content
    


P = ParamSpec("P")
R = TypeVar("R")


class FunctionBlock(Generic[P, R]):
    block: TitleBlock
    func: Callable[P, R]
    
    # def __init__(self, func: Callable[P,R], block_args, *args, **kwargs):
    #     self.func = func
    #     self.block_args = block_args
    #     self.args = args
    #     self.kwargs = kwargs
        
        
    def __call__(self, *args, **kwargs):
        output = self.func(*args, **kwargs)




def decorator(title=None, ttype: TitleType="md", id: str | None = None):        
    def subdecorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):                
            block = TitleBlock(title=title, ttype=ttype, id=id)
            output = func(*args, **kwargs)
            block.append(output)
            return block
        return wrapper
    return subdecorator
  

class block(Generic[P, R]):
        
    
    def __init__(self, title=None, ttype: TitleType="md", id: str | None = None):
        self.block = TitleBlock(title=title, ttype=ttype, id=id)
    
    def __enter__(self):
        return self.block
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass   
    
    @staticmethod
    def list(title=None, ttype: TitleType="md", bullet: BulletType = "-", id: str | None = None):        
        return ListBlock(title=title, ttype=ttype, bullet=bullet, id=id)
    
    
    # def __call__(self, func: Callable[P, R]) -> Callable[P, TitleBlock]:        
    #     @wraps(func)
    #     def wrapper(*args, **kwargs) -> TitleBlock:                
    #         # block = TitleBlock(title=title, ttype=ttype, id=id)
    #         output = func(*args, **kwargs)
    #         self.block.append(output)
    #         return self.block
    #     return wrapper
    
    # @staticmethod
    # def decorator(cls, title=None, ttype: TitleType="md", id: str | None = None):        
    #     def subdecorator(func: Callable[P, BaseBlock]) -> Callable[P, TitleBlock]:
    #         @wraps(func)
    #         def wrapper(*args, **kwargs):                
    #             block = TitleBlock(title=title, ttype=ttype, id=id)
    #             output = func(*args, **kwargs)
    #             block.append(output)
    #             return block
    #         return wrapper
    #     return subdecorator
    
    # @staticmethod
    # def wrap(title=None, ttype: TitleType="md", id: str | None = None):        
    #     return decorator(title=title, ttype=ttype, id=id)
    
    def __call__(self, title=None, ttype: TitleType="md", id: str | None = None):
        return decorator(title=title, ttype=ttype, id=id)
    
    
    
    


