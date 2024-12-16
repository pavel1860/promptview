from uuid import uuid4
from pydantic import BaseModel, Field
from typing import Literal
import json
from typing import Protocol, runtime_checkable


@runtime_checkable
class Renderable(Protocol):
    
    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0)->str:
        """
        Classes conforming to the Renderable Protocol must implement
        a `render` method with the specified arguments.
        """
        ...
        
        

class strblk(str, Renderable):
    
    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
        content = self
        if prefix:
            content = prefix + content
        if postfix:
            content = content + postfix
        if tabs or indent:
            content = " " * (tabs or indent) + content
        return content
    
    
class dictblk(dict, Renderable):
    
    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
        content = json.dumps(self, indent=indent)
        return content

   
class listblk(list):
    
    def render(self, indent=4):
        return json.dumps(self, indent=indent)

class Style(BaseModel):
    prefix: str | None = None
    postfix: str | None = None
    tabs: int = 0
    indent: int = 0

class BaseBlock(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    tag: str | None = Field(default=None, description="The tag for the block")
    bclass: str = Field(default="block", description="The class for the block")
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
    
    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
        return "\n".join([item.render(tabs=tabs+1, indent=indent) for item in self._items])
    
    def __repr__(self) -> str:
        repr_str = super().__repr__()
        return repr_str + "\n" + self.render()
    
    
class TitleBlock(BaseBlock):
    ttype: Literal["xml", "md", "html"] = Field(default="md", description="The style of the title")
    title: str | None = Field(None, description="The title of the block")
    
    def _render_md(self):
        content = super().render()
        return f"## {self.title}\n{content}"
    
    def _render_html(self):
        content = super().render()
        return f"<h2>{self.title}</h2>\n{content}"
    
    def _render_xml(self):
        content = super().render()
        return f"<${self.title}>\n{content}\n</{self.title}>"    

    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
        content = super().render(prefix=prefix, postfix=postfix, tabs=tabs, indent=indent)
        if self.ttype == "md":
            content = f"## {self.title}\n{content}"
        elif self.ttype == "html":
            content = f"<h2>{self.title}</h2>\n{content}"
        elif self.ttype == "xml":
            content = f"<${self.title}>\n{content}\n</{self.title}>"
        else:
            raise ValueError(f"Invalid title style: {self.ttype}")
        return content
    
    
class Block(TitleBlock):
    ...
    
    
    
class ListBlock(BaseBlock):
    bullet: Literal["number", "*", "-"] = Field(default="-", description="The bullet style for the list")
    
    def _get_list_item(self, idx, item):
        if self.bullet == "number":
            return f"{idx+1}. {item}"        
        return f"{self.bullet} {item}"
    
    def _get_prefix(self, idx: int):
        if self.bullet == "number":
            return f"{idx+1}. "
        return f"{self.bullet} "
        
    
    def render(self, prefix: str | None = None, postfix: str | None = None, tabs: int = 0, indent: int = 0):
        return "\n".join([item.render(prefix=self._get_prefix(idx), tabs=tabs, indent=indent) for idx, item in enumerate(self._items)])
