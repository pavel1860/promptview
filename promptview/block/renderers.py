import json
import yaml
from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from promptview.block.block7 import Block



class BaseRenderer(ABC):
    is_block: bool | None = None
    is_inline: bool | None = None
    
    
    def can_render(self, block: "Block") -> bool:
        if self.is_block is not None:
            return self.is_block == block.is_block
        elif self.is_inline is not None:
            return self.is_inline == block.is_inline
        else:
            return True
    
    def render(self, block, content: str, style: dict, depth: int) -> str:
        """
        Render the current block itself.
        """
        raise NotImplementedError("Subclasses must implement this method")
    
    def render_child(self, block_list, content: str, style: dict, depth: int, index: int) -> str:
        """
        Render a child block of a list.
        
        Args:
            block_list: The list of blocks.
            content: The content of the child block.
            style: The style of the child block.
            depth: The depth of the child block.
            index: The index of the child block.
        """
        raise NotImplementedError("Subclasses must implement this method")
        


class RendererRegistry:
    
    
    def __init__(self):
        self._registry = {}

    def register(self, name: str, renderer: BaseRenderer):
        self._registry[name] = renderer

    def get(self, name: str) -> BaseRenderer:
        return self._registry[name]

    def list_renderers(self):
        return list(self._registry.keys());
    
    
class ContentRenderer(BaseRenderer):    
    
    def render(self, block, content: str, style: dict, depth: int) -> str:
        return content
    
    def render_child(self, block_list, content: str, style: dict, depth: int, index: int) -> str:
        return content
    
    
    
    
    # def render(self, block, style: dict, depth: int) -> str:
    #     def indent(text: str) -> str:
    #         return "\n".join([f"{' ' * depth}{line}" for line in text.split("\n")])
    #     return indent(block.sep.join([indent(str(c)) for c in block.content]))
    
        
        
class MarkdownHeaderRenderer(BaseRenderer):
    is_block: bool | None = True
    
    def render(self, block, content: str, style: dict, depth: int) -> str:
        level = min(depth + 1, 6)        
        return f"{'#' * level} {content}"
    
    
class NumberedListRenderer(BaseRenderer):
    is_block: bool | None = False
    
    def render_child(self, block_list, content: str, style: dict, depth: int, index: int) -> str:
        return f"{index + 1}. {content}"
    
    
    
    
