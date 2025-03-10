
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import StyleManager
from typing import Literal, TypedDict, Union





class Renderer:
    
    def __init__(self, style_manager: StyleManager):
        self.style_manager = style_manager
    
    def can_render(self, block: BaseBlock) -> bool:
        raise NotImplementedError("Subclass must implement this method")
    
    def render(self, block: BaseBlock, block_content: str | list[str]) -> str:
        raise NotImplementedError("Subclass must implement this method")
    

    
class RecursiveRenderer:
    
    def __init__(self, style_manager: StyleManager, renderers: list[Renderer]):
        self.style_manager = style_manager
        self.renderers = renderers
    
    def render(self, block: BaseBlock) -> str:        
        item_content = [self.render(item) for item in block.items]
        return self.renderers[0].render(block, item_content)
        
        

BulletType = Literal["number", "alpha", "roman", "roman_lower", "*", "-"]
BlockType = Literal["list", "code", "table", "text"]

class MarkdownStyles(TypedDict):
    title: bool
    block_type: BlockType
    bullet_type: BulletType
    heading_level: int
    indent_depth: bool
    


class MarkdownRenderer(Renderer):
    
    def can_render(self, block: BaseBlock) -> bool:
        return True
    
    def render(self, block: BaseBlock, block_content: str | list[str]) -> str:
        content = ""
        if block.content:
            if block.is_block:
                content = f"{'#' * block.depth} {block.content}" + "\n" + "\n".join(block_content)
            else:
                content = block.content
        content += "\n".join(block_content)
        return content
        





class XMLRenderer(Renderer):
    
    def can_render(self, block: BaseBlock) -> bool:
        return block.tags == ["xml"]
    
    def render(self, block: BaseBlock, block_content: str | list[str]) -> str:
        content = ""
        if block.content:
            if block.is_block:
                if block_content:
                    content = f"<{block.content}>\n" + "\n".join(block_content) + f"\n</{block.content}>"
                else:
                    content = f"<{block.content} />"
            else:
                content = block.content
        else:
            content = "\n".join(block_content)
        
        return content


    
# class ListRenderer(Renderer):
    
#     def can_render(self, block: BaseBlock) -> bool:
#         return block.tags == ["list"]
    
#     def render(self, block: BaseBlock) -> str:
#         return block.content