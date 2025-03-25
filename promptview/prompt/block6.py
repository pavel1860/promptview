from collections import defaultdict
from abc import abstractmethod
import textwrap
from typing import Any, Callable, Generic, List, Literal, Type, TypeVar, Union

from pydantic import BaseModel
from promptview.prompt.style import InlineStyle, BlockStyle, style_manager
from promptview.utils.model_utils import schema_to_ts




ContentType = Union[str , dict , "Block"]
 
    
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



BlockRole = Literal["assistant", "user", "system", "tool"]

class LlmUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ToolCall(BaseModel):
    id: str
    name: str
    tool: dict | BaseModel
    
    @property
    def type(self):
        return type(self.tool)
    
    def to_json(self):
        return self.tool.model_dump_json() if isinstance(self.tool, BaseModel) else json.dumps(self.tool)


MAP_RET = TypeVar("MAP_RET")

class BlockList(list["Block"], Generic[MAP_RET]):
    """
    A list of blocks
    """
    
    def group(self, role: BlockRole | None = None, tags: list[str] | None = None) -> "Block":
        """
        Group the blocks by role and tags
        """
        return Block(items=self, role=role, tags=tags)
    
    def get(self, key: str | list[str], default: Any = None) -> "List[Block]":
        """
        Get the blocks by key
        """
        if isinstance(key, str):
            key = [key]
        return [item for item in self if all(tag in item.tags for tag in key)]
    
    
    def map(self, func: "Callable[[Block], MAP_RET]") -> "list[MAP_RET]":
        """
        Map the blocks by function
        """
        return [func(item) for item in self]
    
    def bmap(self, func: "Callable[[Block], Block]") -> "BlockList":
        """
        Map the blocks by function
        """
        return BlockList([func(item) for item in self])
    
    
    
    
        
class Block:
    """
    A block is a container for content and other blocks.
    """
    
    __slots__ = [
        "content", 
        "tags", 
        "items", 
        "inline_style", 
        "computed_style", 
        "parent",
        "depth",
        "_ctx",
        "run_id",
        "role",
        "name",
        "model",
        "tool_calls",
        "usage",
        "id",
        "db_id",
        "attrs",
    ]
    # tags: list[str]
    # items: list["Block"]
    # inline_style: BlockStyle
    # computed_style: InlineStyle
    # content: Any | None
    # parent: "Block | None"
    # depth: int
    
    def __init__(
        self, 
        content: Any | None = None, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None, 
        attrs: dict | None = None,
        depth: int = 0, 
        parent: "Block | None" = None, 
        dedent: bool = True, 
        items: list["Block"] | None = None,
        ctx: ContextStack | None = None,
        run_id: str | None = None,
        role: BlockRole | None = None,
        name: str | None = None,
        model: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        usage: LlmUsage | None = None,
        id: str | None = None,
        db_id: str | None = None,
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
        self.run_id = run_id
        self.role = role
        self.name = name
        self.model = model
        self.tool_calls = tool_calls
        self.usage = usage
        self.id = id
        self.db_id = db_id
        self.attrs = attrs
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
    
    @property
    def ctx_items(self) -> list["Block"]:
        if self._ctx:
            return self._ctx[-1].items
        else:
            return self.items
    
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
        
    def get(self, key: str | list[str], default: Any = None) -> "BlockList":
        if isinstance(key, str):
            key = [key]
        sel_items = BlockList()
        for item in self.items:
            for k in key:
                if k in item.tags:
                    sel_items.append(item)
                    break
            else:
                sel_items.extend(item.get(key, default))
        return sel_items
    
    def first(self, key: str | list[str], default: Any = None, raise_error: bool = True) -> "Block":
        blocks = self.get(key, default)
        if len(blocks) == 0:
            if raise_error:
                raise ValueError(f"No block found for key {key}")
            else:
                return default
        return blocks[0]
        
        
    def __getitem__(self, idx: int) -> "Block":
        return self.items[idx]
    
    def __len__(self) -> int:
        return len(self.items)
    
    
    def _build_instance(
        self, 
        content: Any, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None,
        attrs: dict | None = None,
        items: list["Block"] | None = None,
        role: BlockRole | None = None,
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
                attrs=attrs,
            )
        if role:
            inst.role = role
        return inst
        
    def __call__(
        self, 
        content: Any | None = None, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None, 
        attrs: dict | None = None,
        **kwargs
    ):
        self.append(content=content, tags=tags, style=style, attrs=attrs, **kwargs)
        return self.items[-1]
    
    
    def append(
        self, 
        content: Any, 
        tags: list[str] | None = None, 
        style: InlineStyle | None = None,
        attrs: dict | None = None,
        items: list["Block"] | None = None,
        role: BlockRole | None = None,
    ):
        inst = self._build_instance(
            content=content, 
            tags=tags, 
            style=style, 
            items=items,
            attrs=attrs,
            role=role,
        )
        self.ctx_items.append(inst)
        # if self._ctx:
        #     self._ctx[-1].items.append(inst)
        # else:
        #     self.items.append(inst)
        return self
    
    
    def merge(self, other: "Block"):
        """
        Merge another block into this one
        """
        self.ctx_items.extend(other.items)
        return self
    
    
    def __itruediv__(self, content: ContentType):
        """
        Append a new item to the block
        """
        self.append(content)
        return self    
    
    def __truediv__(self, content: ContentType):
        """
        Append a new item to the block
        """
        self.append(content)
        return self
    
    def __add__(self, other: "Block | Any"):
        """
        Append a new item to the block
        """
        # TODO: figure out how to merge block content
        if isinstance(other, Block):
            self.merge(other)
        else:
            self.append(other)
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
    
    def model_dump(self, model: Type[BaseModel], format: str = "ts"):    
        if format == "ts":
            content = schema_to_ts(model)
        else:
            content = model.model_json_schema()        
        return self.append(content)

    
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
        tags = ", ".join(self.tags)
        tag = f"[{tags}]" if tags else ""
        role = f" role={self.role}" if self.role else ""
        
        return f"{self.__class__.__name__}({tags}{role}):\n{content}"





class BlockContext:
    """
    A context for managing nested block structures.
    """
    ctx: ContextStack
    
    def __init__(self, root: "Block"):
        self.ctx = ContextStack()
        self.ctx.push(root)
        
    def __call__(self, content: Any, tags: list[str] | None = None, style: InlineStyle | None = None, attrs: dict | None = None, **kwargs):       
        self._append(content, tags, style, attrs)
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
        attrs: dict | None = None,
        items: list["Block"] | None = None
    ):
        inst = Block(
            content=content, 
            tags=tags, 
            style=style, 
            parent=self.ctx[-1],
            depth=len(self.ctx) if self.ctx else 0,
            items=items,
            attrs=attrs,
        )        
        self.ctx[-1].append(inst)
        return inst
    
    
    def __itruediv__(self, content: Any):
        self._append(content)
        return self