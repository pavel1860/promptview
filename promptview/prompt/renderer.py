
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import BulletType, StyleManager
from typing import Any, List, Literal, Protocol, Type, TypedDict, Union

from promptview.utils.string_utils import int_to_roman






class RendererMeta(type):
    
    _renderers: dict[str, Type["Renderer"]] = {}
    
    def __new__(cls, name, bases, dct):        
        renderer = super().__new__(cls, name, bases, dct)
        if name not in ["Renderer", "ContentRenderer", "ItemsRenderer"]:
            if "tags" not in dct:
                raise ValueError("Tags must be defined")
            for tag in renderer.tags:
                # if tag in cls._renderers:
                #     raise ValueError(f"Renderer {tag} already defined")
                cls._renderers[tag] = renderer
        return renderer
    
    def __getitem__(self, key: str) -> Type["Renderer"]:
        return self._renderers[key]


class Renderer(metaclass=RendererMeta):
    tags: list[str]
    target: Literal["content", "items"]
    
    def __call__(self, *args: Any, **kwargs: Any) -> str | List[str]:
        ...



class ContentRenderer(Renderer):
    tags: list[str]
    target = "content"
    
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> str:
        raise NotImplementedError("Subclass must implement this method")
    
    
class ItemsRenderer(Renderer):
    tags: list[str]
    target = "items"
        
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> List[str]:
        raise NotImplementedError("Subclass must implement this method")
    


class MarkdownTitleRenderer(ContentRenderer):
    tags = ["md"]
    
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> str:
        content = ""
        if block.content:
            if block.is_block:
                content = f"{'#' * (depth + 1)} {block.content}" + "\n"
            else:
                content = block.content
        if inner_content:
            content += "\n".join(inner_content)
        return content
        


class MarkdownParagraphRenderer(ItemsRenderer):
    tags = ["md"]
    
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> List[str]:
        return inner_content

class MarkdownListRenderer(ItemsRenderer):
    tags = ["list:number", "list:alpha", "list:roman", "list:roman_lower", "list:*", "list:-"]
    
        
    def _get_prefix(self, bullet_type: BulletType, idx: int) -> str:
        if bullet_type == "" or bullet_type == "number":
            return f"{idx}. "
        elif bullet_type == "alpha":
            return f"{chr(96+idx)}. "
        elif bullet_type == "roman_upper":
            return int_to_roman(idx, upper=True) + ". "
        elif bullet_type == "roman":
            return int_to_roman(idx, upper=False) + ". "
        elif bullet_type == "*":
            return "* "
        elif bullet_type == "-":
            return "- "
        else:
            return f"{bullet_type} "
        
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> List[str]:
        bullet_type = block.inline_style.get("bullet_type", "number")
        if not bullet_type:
            raise ValueError("Bullet type not found")
        return [self._get_prefix(bullet_type, idx) + item for idx, item in enumerate(inner_content)]


class XMLRenderer(ContentRenderer):
    tags = ["xml"]
    
    def __call__(self, block: BaseBlock, inner_content: List[str], depth: int) -> str:
        if not block.content:
            return "\n".join(inner_content) or ""
        if block.is_block:
            if inner_content:
                return f"<{block.content}>\n" + "\n".join(inner_content) + f"\n</{block.content}>"
            else:
                return f"<{block.content} />"        
        return block.content
        


    
# class ListRenderer(Renderer):
    
#     def can_render(self, block: BaseBlock) -> bool:
#         return block.tags == ["list"]
    
#     def render(self, block: BaseBlock) -> str:
#         return block.content

# class MarkdownStyles(TypedDict):
#     title: bool
#     block_type: BlockType
#     bullet_type: BulletType
#     heading_level: int
#     indent_depth: bool
