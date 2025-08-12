import json
import textwrap
import yaml
from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

from promptview.block.types import ContentType



if TYPE_CHECKING:
    from promptview.block.block7 import Block, BaseBlock


class RenderContext:
    def __init__(
        self, 
        block: "BaseBlock | None",
        style: dict, 
        index: int, 
        depth: int,
        parent_ctx: "RenderContext | None" = None,
    ):
        self.block = block
        self.style = style
        self.index = index
        self.depth = depth
        self.parent_ctx = parent_ctx
        
    @property
    def is_list(self) -> bool:
        from promptview.block.block7 import BlockList
        return isinstance(self.block, BlockList)
    
    @property
    def is_context(self) -> bool:
        from promptview.block.block7 import BlockContext
        return isinstance(self.block, BlockContext)
    
    @property
    def is_root(self) -> bool:
        return self.parent_ctx is None
    
    @property
    def is_wrapper(self) -> bool:
        from promptview.block.block7 import BlockContext
        if self.block and isinstance(self.block, BlockContext):
            if not self.block.root:
                return True
        return False

class BaseRenderer(ABC):    
        
    def validate_content(self, content: ContentType) -> bool:
        if isinstance(content, str):
            return True
        elif isinstance(content, int):
            return True
        elif isinstance(content, float):
            return True
        elif isinstance(content, bool):
            return True
        else:
            return False
        
    def validate_inner_content(self, inner_content: str | None) -> bool:
        if inner_content is None:
            return True
        elif isinstance(inner_content, str):
            return True
        else:
            return False
        
    def validate_list_content(self, content: list[str]) -> bool:
        return all(isinstance(c, str) for c in content)
        
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        """
        Render the current block itself.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement render method")
    
    def try_render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        if not self.validate_content(content):
            raise ValueError(f"Invalid content type: {type(content)} in renderer {self.__class__.__name__}")
        if inner_content is not None and not self.validate_inner_content(inner_content):
            raise ValueError(f"Invalid inner content type: {type(inner_content)} in renderer {self.__class__.__name__}")
        return self.render(ctx, content, inner_content)
    
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        """
        Render a list of blocks.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement list render method")
    
    
    def try_render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        if not self.validate_list_content(content):
            content_types = [type(c) for c in content]
            raise ValueError(f"Invalid list content types: {content_types} in renderer {self.__class__.__name__}")
        return self.render_list(ctx, content)
    
    
    def try_render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        if not self.validate_list_content(content):
            content_types = [type(c) for c in content]
            raise ValueError(f"Invalid list content types: {content_types} in renderer {self.__class__.__name__}")
        return self.render_list_layout(ctx, content)
    
    def render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        """
        Render a list of blocks with a layout.
        """
        raise NotImplementedError(f"{self.__class__.__name__} must implement list layout render method")
    
    


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
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        head_content = ""
        if isinstance(content, str):
            head_content = content
        elif isinstance(content, int):
            head_content = str(content)
        elif isinstance(content, float):
            head_content = str(content)
        elif isinstance(content, bool):
            head_content = str(content)
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
        if head_content:
            if inner_content:
                inner_content = textwrap.indent(inner_content, " ")
            return f"{head_content}\n{inner_content}" if inner_content else head_content
        elif inner_content:
            return inner_content
        else:
            return ""
        
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [self.render(ctx, c) for c in content]
        


class ListColumnLayoutRenderer(BaseRenderer):
    
    def render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        return "\n".join(content)
    

class ListRowLayoutRenderer(BaseRenderer):
    
    def render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        return " ".join(content)


class ListColumnTupleLayoutRenderer(BaseRenderer):
    
    def render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        return ",\n".join(content)

class ListStreamLayoutRenderer(BaseRenderer):
    
    def render_list_layout(self, ctx: RenderContext, content: list[str]) -> str:
        return "".join(content)
    
    
    
    # def render(self, block, style: dict, depth: int) -> str:
    #     def indent(text: str) -> str:
    #         return "\n".join([f"{' ' * depth}{line}" for line in text.split("\n")])
    #     return indent(block.sep.join([indent(str(c)) for c in block.content]))
    
        
        
class MarkdownHeaderRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: ContentType | None = None) -> str:
        level = min(ctx.depth + 1, 6)        
        header_content = f"{'#' * level} {content}"
        if inner_content is not None and isinstance(inner_content, str):
            return f"{header_content}\n{inner_content}"
        else:
            return header_content
    
    
class NumberedListRenderer(BaseRenderer):
    
    # def _get_prefix(self, ctx: RenderContext) -> str:
    #     idx_list = []
    #     curr = ctx.parent_ctx
    #     while curr:
    #         if curr.parent_ctx and curr.parent_ctx.block and curr.style.get("list-format") == "numbered-list":                
    #             if not curr.is_list:
    #                 idx_list.append(curr.index)
    #             curr = curr.parent_ctx
    #         else:
    #             break
    #     if not idx_list:
    #         return ""
    #     return ".".join([str(i + 1) for i in reversed(idx_list)]) + "."
    
    def _get_prefix(self, ctx: RenderContext) -> str:
        idx_list = []
        curr = ctx.parent_ctx
        while curr:
            if curr.is_context and curr.style.get("list-format") == "numbered-list" and not curr.is_root and curr.parent_ctx.style.get("list-format") == "numbered-list":
                idx_list.append(curr.index)
            curr = curr.parent_ctx
            
        if not idx_list:
            return ""
        return ".".join([str(i + 1) for i in reversed(idx_list)]) + "."

    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"{ctx.index + 1}. {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        prefix = self._get_prefix(ctx)
        postfix = "." if not prefix else ""
        return [f"{prefix}{i + 1}{postfix} {c}" for i, c in enumerate(content)]
    
    
class AsteriskListRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"* {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [f"* {c}" for c in content]
    

class DashListRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"- {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [f"- {c}" for c in content]
    
    
class PlusListRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"+ {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [f"+ {c}" for c in content]
    
class BulletListRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"• {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [f"• {c}" for c in content]


class CheckboxListRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        return f"[ ] {content}"
    
    def render_list(self, ctx: RenderContext, content: list[str]) -> list[str]:
        return [f"[ ] {c}" for c in content]

  
class XmlTitleRenderer(BaseRenderer):
    
    def render(self, ctx: RenderContext, content: ContentType, inner_content: str | None = None) -> str:
        
        if ctx.block.attrs:
            attrs = " " + " ".join([f"{k}=\"{v}\"" for k, v in ctx.block.attrs.items()])
        else:
            attrs = ""
        
        if inner_content is not None:
            inner_content = textwrap.indent(inner_content, " ")
            return f"<{content}{attrs}>\n{inner_content}\n</{content}>"
        else:
            return f"<{content}{attrs} />"
    
    
    
    
    
    
