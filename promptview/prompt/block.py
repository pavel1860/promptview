from abc import abstractmethod
from uuid import uuid4
from pydantic import BaseModel, Field
from typing import Literal
import json
from typing import Protocol, runtime_checkable




class Style(BaseModel):
    bclass: str | None = Field(default=None, description="The class for the block")
    ttype: Literal["xml", "md", "html"] | None = Field(default=None, description="The style of the title")
    bullet: Literal["number", "*", "-"] | None = Field(default=None, description="The bullet style for the list")
    prefix: str | None = Field(default=None, description="prefix to add to the block title")
    postfix: str | None = Field(default=None, description="postfix to add to the block title")
    tabs: int = Field(default=0, description="number of tabs to add to the block content")
    indent: int = Field(default=0, description="number of spaces to indent the block content")
    dropout: float = Field(default=0.0, description="dropout probability for the block")



class StyleManager():
    
    def __init__(self, styles: dict):
        self.styles = styles
        
    def get(self, block_id):
        style_dict = self.styles.get(block_id, None)
        if style_dict is None:
            return None
        return Style(**style_dict)
    
    def add(self, style_dict: dict):
        self.styles.update(style_dict)
    
    def get_style(self, block: "BaseBlock"):
        style = block.get_style(style=self.get(block.id))
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
        
        

class strblk(str, Renderable):
    
    def render(self, style: Style):
        content = self
        if style.prefix:
            content = style.prefix + content
        if style.postfix:
            content = content + style.postfix
        if style.tabs or style.indent:
            content = " " * (style.tabs or style.indent) + content
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
        new_style.tabs += 1
        return "\n".join([item.render(style=new_style) for item in self._items])
    
    def __repr__(self) -> str:
        repr_str = super().__repr__()
        return repr_str + "\n" + self.render()
    
    
class TitleBlock(BaseBlock):
    ttype: Literal["xml", "md", "html"] = Field(default="md", description="The style of the title")
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
            content = f"## {self.title}\n{content}"
        elif style.ttype == "html":
            content = f"<h2>{self.title}</h2>\n{content}"
        elif style.ttype == "xml":
            content = f"<{self.title}>\n{content}\n</{self.title}>"
        else:
            raise ValueError(f"Invalid title style: {self.ttype}")
        return content

    def render(self, style: Style | None = None):
        # style = self.get_style(style)
        style = style_manager.get_style(self)
        content = super().render(style=style)
        if self.title:
            content = self._render_title(content, style)        
        return content
    
    
class Block(TitleBlock):
    ...
    
    
    
class ListBlock(TitleBlock):
    bullet: Literal["number", "*", "-"] = Field(default="-", description="The bullet style for the list")
    
    def _get_list_item(self, idx, item):
        if self.bullet == "number":
            return f"{idx+1}. {item}"        
        return f"{self.bullet} {item}"
    
    def _get_prefix(self, idx: int):
        if self.bullet == "number":
            return f"{idx+1}. "
        return f"{self.bullet} "
    
    def get_style(self, style: Style | None = None) -> Style:        
        curr_style = Style(bullet=self.bullet)
        if style is not None:
            curr_style = curr_style.model_copy(update=style.model_dump())
        return curr_style
    
    def render(self, style: Style | None = None):
        # new_style = self.get_style(style)
        new_style = style_manager.get_style(self)
        new_style.tabs += 1
        content = "\n".join([self._get_list_item(idx, item.render(style=new_style)) for idx, item in enumerate(self._items)])
        if self.title:
            content = self._render_title(content, new_style)                    
        return content
    # def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
    #     return "\n".join([item.render(prefix=self._get_prefix(idx), tabs=tabs, indent=indent) for idx, item in enumerate(self._items)])
