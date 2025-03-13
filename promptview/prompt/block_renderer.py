
from promptview.prompt.renderer import ItemsRenderer, MarkdownListRenderer, MarkdownParagraphRenderer, MarkdownTitleRenderer, ContentRenderer, Renderer
from promptview.prompt.style import InlineStyle, BlockStyle, StyleManager, UndefinedTagError
from typing import TYPE_CHECKING, List, Literal, Type, TypedDict, Union
from promptview.prompt.block4 import BaseBlock


class RenderersClassDict(TypedDict):
    content: Type[ContentRenderer] | None
    items: Type[ItemsRenderer] | None

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
        
    def set_renderer(self, renderer: Type[Renderer]):
        if renderer.target == "content" and not isinstance(self._content_renderer, renderer):
            self._content_renderer = renderer() # type: ignore
        elif renderer.target == "items" and not isinstance(self._items_renderer, renderer):
            self._items_renderer = renderer() # type: ignore
    
    def render_content(self, block: BaseBlock, items_content: List[str]) -> str:
        return self._content_renderer(block, items_content, self._depth)

    def render_items(self, block: BaseBlock, inner_content: List[str]) -> List[str]:
        return self._items_renderer(block, inner_content, self._depth)
    
    
    def copy(self, replace: RenderersClassDict | None = None, inc_depth: bool = True) -> "RendererContext":
        content_renderer = self._content_renderer
        items_renderer = self._items_renderer
        if replace is not None:
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
        ctx = parent_ctx.copy() if parent_ctx else RendererContext(
            MarkdownTitleRenderer(),
            MarkdownParagraphRenderer(),
            block.is_wrapper,
        )
        
        for tag in block.inline_style.style:
            try:
                renderer_cls = self.renderer_lookup[tag]
            except KeyError:
                raise UndefinedTagError(f"Tag {tag} not found in renderer lookup. Implement a renderer for this tag.")
            else:
                ctx.set_renderer(renderer_cls)
        return ctx
        
        
    def build_ctx2(self, block: BaseBlock, parent_ctx: "RendererContext | None" = None) -> "RendererContext":
        target_classes: RenderersClassDict = {
            "content": MarkdownTitleRenderer,
            "items": MarkdownParagraphRenderer
        } if parent_ctx is None else {"content": None, "items": None}
        
            
        for tag in block.inline_style.style:
            try:
                renderer_cls = self.renderer_lookup[tag]
            except KeyError:
                raise UndefinedTagError(f"Tag {tag} not found in renderer lookup. Implement a renderer for this tag.")
            else:
                target_classes[renderer_cls.target] = renderer_cls # type: ignore
        
        
        ctx = parent_ctx.copy(target_classes, inc_depth=block.is_wrapper == False) if parent_ctx else RendererContext(
            target_classes["content"]() if target_classes["content"] is not None else None, 
            target_classes["items"]() if target_classes["items"] is not None else None,       
            block.is_wrapper,            
        )
        if ctx._content_renderer is None or ctx._items_renderer is None:
            raise ValueError("No renderer found for content or items")         
        return ctx
        

    def render(self, block: BaseBlock, ctx: RendererContext | None = None) -> str:        
        ctx = self.build_ctx(block, ctx)
        items = [self.render(
                item, 
                ctx,
            ) for item in block.items]
        items_content = ctx.render_items(block, items)
        return ctx.render_content(block, items_content)