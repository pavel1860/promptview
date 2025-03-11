from promptview.prompt.block4 import BaseBlock
from promptview.prompt.renderer import ItemsRenderer, MarkdownListRenderer, MarkdownTitleRenderer, BlockRenderer, Renderer
from promptview.prompt.style import StyleConfig, StyleManager
from typing import Literal, Type, TypedDict, Union




class RendererContext:
    _content_renderer: BlockRenderer
    _items_renderer: ItemsRenderer 
    
    def __init__(self, content_renderer: BlockRenderer, items_renderer: ItemsRenderer):
        self._content_renderer = content_renderer
        self._items_renderer = items_renderer
    
    
    def render_content(self, block: BaseBlock, items_content: str) -> str:
        return self._content_renderer(block, items_content)

    def render_items(self, items: list[str]) -> str:
        return self._items_renderer(items)
    
    
    def get_class_dict(self) -> dict[str, Type[Renderer]]:
        return {
            "content": self._content_renderer.__class__,
            "items": self._items_renderer.__class__
        }
        
        
class RenderersDict(TypedDict):
    content: Type[BlockRenderer]
    items: Type[ItemsRenderer]


class BlockTreeRenderer:
    
    def __init__(self, style_manager: StyleManager, renderers: list[Type[Renderer]]):
        self.style_manager = style_manager
        self.renderers = renderers
        self.renderer_lookup = {tag: renderer for renderer in renderers for tag in renderer.tags}        
        
        
    def build_ctx(self, style: StyleConfig, parent: "RendererContext | None" = None) -> "RendererContext":        
        if parent is not None:
            target_classes: dict[str, Type[Renderer]] = parent.get_class_dict()
        else:
            target_classes: dict[str, Type[Renderer]] = {
                "content": MarkdownTitleRenderer,
                "items": MarkdownListRenderer
            }
        for tag in style:
            renderer_cls = self.renderer_lookup[tag]
            if renderer_cls:
                target_classes[renderer_cls.target] = renderer_cls
        if target_classes["content"] is None or target_classes["items"] is None:
            raise ValueError("No renderer found for content or items")
        return RendererContext(
            target_classes["content"](), 
            target_classes["items"]()
        ) 
        

    def render(self, block: BaseBlock, ctx: RendererContext) -> str:        
        ctx = self.build_ctx(block.inline_style, ctx)
        items = [self.render(item, ctx) for item in block.items]
        items_content = ctx.render_items(items)
        return ctx.render_content(block, items_content)