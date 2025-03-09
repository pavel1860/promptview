import json
import textwrap
from typing import Literal, Type
from promptview.prompt.block4 import BaseBlock, BlockContext
from promptview.utils.string_utils import int_to_roman

        
        
TitleType = Literal["md", "xml"]
BulletType = Literal["number", "alpha", "roman", "roman_upper", "*", "-"]     





class Block(BaseBlock):    
    indent: int = 0
    title: TitleType | None = None
    bullet: BulletType | None = None
    
    
    def __init__(
        self,
        _: Type[None] | None = None,
        tags: list[str] | None = None,                
        bullet: BulletType | None = None,
        indent: int = 0,
        depth: int = 1,
    ):
        super().__init__(tags, depth)                
        self.bullet = bullet
        self.indent = indent
    
    def _get_prefix(self, idx: int):
        bullet_type = self.bullet
        if bullet_type is None:
            return ""
        elif bullet_type == "number":
            return f"{idx}. "
        elif bullet_type == "alpha":
            return f"{chr(96+idx)}. "
        elif bullet_type == "roman_upper":
            return int_to_roman(idx, upper=True) + ". "
        elif bullet_type == "roman":
            return int_to_roman(idx, upper=False) + ". "
        return f"{bullet_type} "
    
    def render(self) -> str:        
        return "\n".join([self._get_prefix(i) + item.render() for i, item in enumerate(self.items)])
    
    def parse(self, text: str):
        return text



         
class StrBlock(Block):    
    content: str
    indent: int = 0
    title: TitleType | None = None
    
    
    def __init__(
        self,
        content: str,
        tags: list[str] | None = None,                
        title: TitleType | None = None,
        bullet: BulletType | None = None,
        indent: int = 0,
        dedent: bool = True,
        depth: int = 1,
    ):
        super().__init__(tags, bullet, indent, depth)
        
        if content is not None:
            content = textwrap.dedent(content).strip() if dedent else content
        self.content = content
        self.title = title
        
    def render(self) -> str:
        content = self.content
        if content and self.title:
            if self.title == "md":
                content = f"{'#' * self.depth} {self.content}"
            elif self.title == "xml":
                content = f"<{self.content}>"
        item_content = super().render()
        if item_content:
            content = content + "\n" + item_content
        
        return content
    
    
    
    def parse(self, text: str):
        return self.content


# class StrBlock(BaseBlock):
    
#     content: str | None
#     indent: int = 0
#     title: TitleType | None = None
#     bullet: BulletType | None = None
    
    
#     def __init__(
#         self,
#         content: str | None = None,
#         tags: list[str] | None = None,                
#         title: TitleType | None = None,
#         bullet: BulletType | None = None,
#         indent: int = 0,
#         dedent: bool = True,
#         depth: int = 1,
#     ):
#         super().__init__(tags, depth)
        
#         if content is not None:
#             content = textwrap.dedent(content).strip() if dedent else content
#         self.content = content
#         self.title = title
#         self.bullet = bullet
#         self.indent = indent
    
#     def _get_prefix(self, idx: int):
#         bullet_type = self.bullet
#         if bullet_type == "number":
#             return f"{idx}. "
#         elif bullet_type == "alpha":
#             return f"{chr(96+idx)}. "
#         elif bullet_type == "roman_upper":
#             return int_to_roman(idx, upper=True) + ". "
#         elif bullet_type == "roman":
#             return int_to_roman(idx, upper=False) + ". "
#         return f"{bullet_type} "
    

        
#     def render(self):
#         content = self.content
#         if content and self.title:
#             if self.title == "md":
#                 content = f"{'#' * self.depth} {self.content}"
#             elif self.title == "xml":
#                 content = f"<{self.content}>"
        
#         if self.items:
#             if self.bullet:
#                 item_content = "\n".join([self._get_prefix(i) + item.render() for i, item in enumerate(self.items)])
#             else:
#                 item_content = "\n".join([item.render() for item in self.items])
#             if not content:
#                 content = item_content
#             else:
#                 # content = content + "\n" + textwrap.indent(item_content, " " * (self.indent if self.indent else self.depth))
#                 content = content + "\n" + textwrap.indent(item_content, " " * (self.indent if self.indent else self.depth))
#         return content
    
    
    
#     def parse(self, text: str):
#         return self.content
        
    
    # def __repr__(self):
    #     return "StrBlock(\n" + self.render() + "\n)"
    

   
    
    

class DictBlock(BaseBlock):
    
    content: dict
    def __init__(self, content: dict, tags: list[str] | None = None, depth: int = 1):
        super().__init__(tags, depth)
        self.content = content
        
        
    def render(self):
        return json.dumps(self.content, indent=2)
    
    
    
    
    


class block(BlockContext):
    
    
    def __new__(cls, *args, **kwargs):
        inst = super().__new__(cls)
        inst.register(str, StrBlock)
        inst.register(dict, DictBlock)
        return inst
    
    def __init__(
        self,
        content: str | None = None,
        tags: list[str] | None = None,                
        title: TitleType | None = None,
        bullet: BulletType | None = None,
        indent: int = 0,
        dedent: bool = True,
        # depth: int = 1
    ):
        super().__init__(content, tags, title, bullet, indent, dedent)
        
        
    def __call__(
        self,
        content: str | None = None,
        tags: list[str] | None = None,                
        title: TitleType | None = None,
        bullet: BulletType | None = None,
        indent: int = 0,
        dedent: bool = True,
        # depth: int = 1
    ):
        return super().__call__(content, tags, title, bullet, indent, dedent)
    
    
    
    
    