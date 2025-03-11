
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import BulletType, StyleManager
from typing import Any, List, Literal, Protocol, TypedDict, Union

from promptview.utils.string_utils import int_to_roman




class Renderer(Protocol):
    tags: list[str]
    target: Literal["content", "items"]
    
    def __call__(self, *args: Any, **kwargs: Any) -> str:
        ...

    


class BlockRenderer(Renderer):
    tags: list[str]
    target = "content"
    
    def __call__(self, block: BaseBlock, inner_content: str | None = None) -> str:
        raise NotImplementedError("Subclass must implement this method")
    
class ItemsRenderer(Renderer):
    tags: list[str]
    target = "items"
        
    def __call__(self, items: list[str]) -> str:
        raise NotImplementedError("Subclass must implement this method")
    


class MarkdownTitleRenderer(BlockRenderer):
    tags = ["md"]
    
    def __call__(self, block: BaseBlock, inner_content: str | None = None) -> str:
        content = ""
        if block.content:
            if block.is_block:
                content = f"{'#' * block.depth} {block.content}" + "\n"
            else:
                content = block.content
        if inner_content:
            content += inner_content
        return content
        


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
        
    def __call__(self, block: List[str]) -> str:
        return "\n".join([self._get_prefix(bullet_type, idx) + item for idx, item in enumerate(block)])


class XMLRenderer(BlockRenderer):
    tags = ["xml"]
    
    def __call__(self, block: BaseBlock, inner_content: str | None = None) -> str:
        if not block.content:
            return inner_content or ""
        if block.is_block:
            if inner_content:
                return f"<{block.content}>\n" + inner_content + f"\n</{block.content}>"
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
