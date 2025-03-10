
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import StyleManager





class Renderer:
    
    def __init__(self, style_manager: StyleManager):
        self.style_manager = style_manager
    
    def can_render(self, block: BaseBlock) -> bool:
        raise NotImplementedError("Subclass must implement this method")
    
    def render(self, block: BaseBlock) -> str:
        raise NotImplementedError("Subclass must implement this method")
    

    
class RecursiveRenderer(Renderer):
    
    def __init__(self, style_manager: StyleManager, renderers: list[Renderer]):
        self.style_manager = style_manager
        self.renderers = renderers
    
    def render(self, block: BaseBlock) -> str:
        if block.items:
            for item in block.items:
                self.render(item)
        else:
            return block.content
        
        




class MarkdownRenderer(Renderer):
    
    def can_render(self, block: BaseBlock) -> bool:
        return True
    
    def render(self, block: BaseBlock) -> str:
        content = block.content
        title_style = block.get_style('title', self.title)
        if content:
            if item_content:
                if title_style == "md":
                    heading_level = self.get_style('heading_level', self.depth)
                    return f"{'#' * heading_level} {content}" + "\n" + item_content                
                elif title_style == "xml":                
                    return f"<{content}>{item_content}</{content}>"
                return content + "\n" + item_content
            else:
                if title_style == "md":
                    heading_level = self.get_style('heading_level', self.depth)
                    return f"{'#' * heading_level} {content}"
                elif title_style == "xml":                
                    return f"<{content} />"
                return content
        else:
            return item_content
    
    
    
class ListRenderer(Renderer):
    
    def can_render(self, block: BaseBlock) -> bool:
        return block.tags == ["list"]
    
    def render(self, block: BaseBlock) -> str:
        return block.content