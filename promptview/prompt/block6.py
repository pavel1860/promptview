from collections import defaultdict
from abc import abstractmethod
import textwrap
from typing import Any, List, Type
from promptview.prompt.style import InlineStyle, BlockStyle, style_manager


    
    
class ContextStack:
    """
    A stack-based context for managing nested block structures.
    """
    _ctx_stack: "list[Block]"
    
    def __init__(self):
        self._ctx_stack = []
        
    def __getitem__(self, idx: int) -> "Block":
        return self._ctx_stack[idx]
    
    def __len__(self) -> int:
        return len(self._ctx_stack)
    
    def root(self) -> "Block":
        if not self._ctx_stack:
            raise ValueError("No context stack")
        return self._ctx_stack[0]
    
    def push(self, block: "Block"):
        self._ctx_stack.append(block)
        
    def pop(self):
        return self._ctx_stack.pop()
    
    def top(self):
        return self._ctx_stack[-1]



    
    
        
class Block:
    
    tags: list[str]
    items: list["Block"]
    inline_style: BlockStyle
    computed_style: InlineStyle
    content: Any | None
    parent: "Block | None"
    
    def __init__(
        self, 
        content: Any | None = None, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None, 
        depth: int = 0, 
        parent: "Block | None" = None, 
        dedent: bool = True, 
        items: list["Block"] | None = None,
        ctx: ContextStack | None = None,
    ):
        if dedent and isinstance(content, str):
            content = textwrap.dedent(content).strip()
        self.content = content
        self.tags = tags or []
        self.items = items or []
        self.depth = depth or 0
        self.inline_style = BlockStyle(style)
        self.parent = parent
        self._ctx = ctx
        
    # def __call__(
    #     self, 
    #     content: Any | None = None, 
    #     tags: list[str] | None = None, 
    #     style: InlineStyle | None = None, 
    #     depth: int = 0, 
    #     parent: "BaseBlock | None" = None, 
    #     dedent: bool = True, 
    #     items: list["BaseBlock"] | None = None
    # ):
    #     pass
    
    def __enter__(self):
        if self._ctx is None:
            self._ctx = ContextStack()
        self._ctx.push(self)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self._ctx is None:
            raise ValueError("No context stack")
        if len(self._ctx) > 1:
            self._ctx.pop()
        
    def get(self, key: str | list[str], default: Any = None) -> Any:
        if isinstance(key, str):
            key = [key]
        sel_items = []
        for item in self.items:
            for k in key:
                if k in item.tags:
                    sel_items.append(item)
                    break
            else:
                sel_items.extend(item.get(key, default))
        return sel_items
    
    def __getitem__(self, idx: int) -> "Block":
        return self.items[idx]
    
    
    def _build_instance(
        self, 
        content: Any, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None,
        items: list["Block"] | None = None,
    ):
        if isinstance(content, Block):
            return content
        inst = Block(
                content=content, 
                tags=tags, 
                style=style, 
                parent=self._ctx[-1] if self._ctx else self,
                depth=len(self._ctx) if self._ctx else 0,
                items=items,
                ctx=self._ctx,
            )
        return inst
        
    def __call__(self, content: Any, tags: list[str] | None = None, style: InlineStyle | None = None, **kwargs):
        inst = self.append(content=content, tags=tags, style=style, **kwargs)
        return inst
    
    def append(
        self, 
        content: Any, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None,
        items: list["Block"] | None = None
    ):
        inst = self._build_instance(
            content=content, 
            tags=tags, 
            style=style, 
            items=items,
        )
        if self._ctx:
            self._ctx[-1].items.append(inst)
        else:
            self.items.append(inst)
        return inst
    
    
    def __itruediv__(self, content: Any):
        self.append(content)
        return self    
        
    # def append(self, item: "Block | Any"):
    #     self.items.append(item)
    #     return item
    
    @property
    def is_block(self) -> bool:
        return len(self.items) > 0
    
    @property
    def is_wrapper(self) -> bool:
        return self.content is None and len(self.items) > 0
    
    @property
    def is_inline(self) -> bool:
        return len(self.items) == 0
    
    def add_style(self, **style_props: Any) -> "Block":
        """
        Add inline style properties to this block
        """
        self.inline_style.update(style_props)
        return self

    
    def get_style(self, property_name: str, default: Any = None) -> Any:
        """
        Get a computed style property value
        """
        return self.inline_style.get(property_name, default)
    
    
    def render(self) -> str:
        from promptview.prompt.block_renderer import BlockRenderer
        from promptview.prompt.renderer import RendererMeta
        rndr = BlockRenderer(style_manager, RendererMeta._renderers)
        return rndr.render(self)
    
      
    def __repr__(self) -> str:
        content = self.render()
        return f"{self.__class__.__name__}():\n{content}"





class BlockContext:
    """
    A context for managing nested block structures.
    """
    ctx: ContextStack
    
    def __init__(self, root: "Block"):
        self.ctx = ContextStack()
        self.ctx.push(root)
        
    def __call__(self, content: Any, tags: list[str] | None = None, style: InlineStyle | None = None, **kwargs):       
        self._append(content, tags, style)
        return self
    
    @property
    def root(self):
        return self.ctx.root()
    
    
    @property
    def last(self):
        """
        The last block in the context stack
        """
        if not self.ctx:
            raise ValueError("No context stack")
        if not self.ctx[-1].items:
            return self.ctx[-1]
        return self.ctx[-1].items[-1]
    
    
    def _append(
        self, 
        content: Any, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None,
        items: list["Block"] | None = None
    ):
        inst = Block(
            content=content, 
            tags=tags, 
            style=style, 
            parent=self.ctx[-1],
            depth=len(self.ctx) if self.ctx else 0,
            items=items,
        )        
        self.ctx[-1].append(inst)
        return inst
    
    
    def __itruediv__(self, content: Any):
        self._append(content)
        return self