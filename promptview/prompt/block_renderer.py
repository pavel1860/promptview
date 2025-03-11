from promptview.prompt.block4 import BaseBlock
from promptview.prompt.renderer import ItemsRenderer, MarkdownListRenderer, MarkdownParagraphRenderer, MarkdownTitleRenderer, ContentRenderer, Renderer
from promptview.prompt.style import InlineStyle, BlockStyle, StyleManager
from typing import List, Literal, Type, TypedDict, Union



class RenderersClassDict(TypedDict):
    content: Type[ContentRenderer]
    items: Type[ItemsRenderer]

class RendererContext:
    _content_renderer: ContentRenderer
    _items_renderer: ItemsRenderer 
    is_wrapper: bool
    _depth: int
    
    def __init__(self, content_renderer: ContentRenderer, items_renderer: ItemsRenderer, is_wrapper: bool, depth: int = 0):
        self._content_renderer = content_renderer
        self._items_renderer = items_renderer
        self._depth = depth
        self.is_wrapper = is_wrapper
    
    def render_content(self, block: BaseBlock, items_content: List[str]) -> str:
        return self._content_renderer(block, items_content, self._depth)

    def render_items(self, block: BaseBlock, inner_content: List[str]) -> List[str]:
        return self._items_renderer(block, inner_content, self._depth)
    
    
    def copy(self, replace: RenderersClassDict, inc_depth: bool = True) -> "RendererContext":
        content_renderer = self._content_renderer
        items_renderer = self._items_renderer
        if replace["content"] is not None and not isinstance(content_renderer, replace["content"]):
            content_renderer = replace["content"]()
        if replace["items"] is not None and not isinstance(items_renderer, replace["items"]):
            items_renderer = replace["items"]()   
            
        depth = self._depth
        if inc_depth and not self.is_wrapper:
            depth += 1     
        return RendererContext(content_renderer, items_renderer, False, depth)
    
    
    def get_class_dict(self) -> dict[str, Type[Renderer]]:
        return {
            "content": self._content_renderer.__class__,
            "items": self._items_renderer.__class__
        }
        
        


class BlockRenderer:
    
    renderer_lookup: dict[str, Type[Renderer]]
    
    def __init__(self, style_manager: StyleManager, renderer_lookup: dict[str, Type[Renderer]]):
        self.style_manager = style_manager
        self.renderer_lookup = renderer_lookup
        
        
    def build_ctx(self, block: BaseBlock, parent_ctx: "RendererContext | None" = None) -> "RendererContext":        
        target_classes: RenderersClassDict = {
            "content": MarkdownTitleRenderer,
            "items": MarkdownParagraphRenderer
        }
        for tag in block.inline_style.style:
            renderer_cls = self.renderer_lookup[tag]
            target_classes[renderer_cls.target] = renderer_cls # type: ignore
        if target_classes["content"] is None or target_classes["items"] is None:
            raise ValueError("No renderer found for content or items")        
        
        return parent_ctx.copy(target_classes, inc_depth=block.is_wrapper == False) if parent_ctx else RendererContext(
            target_classes["content"](), 
            target_classes["items"](),       
            block.is_wrapper,            
        ) 
        

    def render(self, block: BaseBlock, ctx: RendererContext | None = None) -> str:        
        ctx = self.build_ctx(block, ctx)
        items = [self.render(
                item, 
                ctx,
            ) for item in block.items]
        items_content = ctx.render_items(block, items)
        return ctx.render_content(block, items_content)