from typing import TYPE_CHECKING, Any, Generic, List, Protocol, Set, TypeVar
from pydantic_core import core_schema
from pydantic import BaseModel, GetCoreSchemaHandler
from promptview.block.block_renderer2 import render
from promptview.block.util import LlmUsage, StreamEvent, StreamStatus, ToolCall
if TYPE_CHECKING:
    from promptview.model.block_model import BlockModel
    from promptview.model.model import SelectQuerySet



ContentType = str | int | float | bool | None

CHUNK_TYPE = TypeVar("CHUNK_TYPE", str, int, float, bool, None)

class Chunk(StreamEvent):
    
    __slots__ = [
        "content",
        "logprob",
        "event",
        "metadata",
    ]
    
    def __init__(self, content: ContentType, logprob: float = 0, event: StreamStatus | None = None, metadata: dict | None = None):
        self.content: ContentType = content 
        self.logprob: float = logprob
        self.event: StreamStatus | None = event
        self.metadata: dict | None = metadata
        
    def merge(self, other: "Chunk") -> "ChunkList":
        return ChunkList([self, other])
    
    def rmerge(self, other: "Chunk") -> "ChunkList":
        return ChunkList([other, self])
    
    def __add__(self, other: "Chunk") -> "ChunkList":
        return self.merge(other)
    
    def __radd__(self, other: "Chunk") -> "ChunkList":
        return self.rmerge(other)
    
    def __str__(self) -> str:
        return str(self.content)
    
    def __repr__(self) -> str:
        return f"Chunk({self.content}: {self.logprob})"
    
    
        
        


class ChunkList(list[Chunk]):
    
    def __init__(self, chunks: list[Chunk]):
        super().__init__(chunks)
         
    
    @property
    def logprob(self) -> float:
        return sum(chunk.logprob for chunk in self)
    
    
    def __repr__(self) -> str:
        return f"ChunkList({[chunk.content for chunk in self]}: {self.logprob})"



class ContextStack:
    """
    A stack-based context for managing nested block structures.
    """
    _ctx_stack: "list[Block]"
    
    def __init__(self):
        self._ctx_stack = []
        
        
    @property
    def top(self):
        return self._ctx_stack[-1]
    
    @property
    def root(self) -> "Block":
        if not self._ctx_stack:
            raise ValueError("No context stack")
        return self._ctx_stack[0]
        
    def __getitem__(self, idx: int) -> "Block":
        return self._ctx_stack[idx]
    
    def __len__(self) -> int:
        return len(self._ctx_stack)
    
    
    
    def push(self, block: "Block"):
        self._ctx_stack.append(block)
        
    def pop(self):
        return self._ctx_stack.pop()
    


def children_to_blocklist(children: list["Block"] | tuple["Block", ...] | None) -> "BlockList":
    if children is None:
        return BlockList([])
    if isinstance(children, BlockList):
        return children
    return BlockList(list(children))

def to_chunk(content: ContentType | Chunk) -> Chunk:
    if isinstance(content, Chunk):
        return content
    return Chunk(content)


def parse_style(style: str | List[str] | None) -> List[str]:
    if isinstance(style, str):
        return list(style.split(" "))
    elif type(style) is list:
        return style
    else:
        return []


class Block(StreamEvent):
    """
    Block(content, children=None, role=None, tags=None, style=None, ...)

    A composable building block for programmatic prompt and string construction.

    The Block class enables flexible, component-based prompt engineering in Python,
    inspired by React/HTML composition. It separates content from style (e.g., markdown,
    XML, JSON, numbered lists), supports tagging, and allows for easy reuse and
    manipulation of prompt components. Blocks can be nested, stacked, and combined
    horizontally or vertically, making it easy to build complex, context-aware prompts
    for LLMs and other applications.

    Key Features:
    - Compose prompts using nested, reusable blocks
    - Separate content from formatting via a style system
    - Add roles, tags, and metadata for context and organization
    - Horizontal and vertical stacking (hstack, vstack, +, /=, +=)
    - Context manager support for building nested structures
    - Designed for dynamic, programmatic prompt generation

    Args:
        *chunks: Content pieces (str, int, float, bool, None, or Chunk)
        children: Optional list of child Blocks
        role: Optional string indicating the role (e.g., "user", "assistant")
        tags: Optional list of tags for organization or filtering
        style: Optional style string or list (e.g., "markdown-header", "numbered-list")
        attrs: Optional dictionary of additional attributes
        depth: Nesting depth (used internally)
        parent: Parent Block (used internally)
        run_id, model, tool_calls, usage, id, db_id, sep, event, metadata: Advanced/streaming options

    Example:
        >>> block = Block("Hello", "World", style="markdown-header", tags=["greeting"])
        >>> print(block.render())
        # Hello World

        >>> with Block("List", style="numbered-list") as lst:
        ...     lst /= "Item 1"
        ...     lst /= "Item 2"
        >>> print(lst.render())
        1. Item 1
        2. Item 2

    See Also:
        - hstack, vstack, ihstack: for block composition
        - append, extend, add_child: for adding content/children
        - render(): to produce the final string output
        - Context manager usage for nested block construction
    """
    
    __slots__ = [
        "content",
        "children",
        "role",        
        "tags",
        "styles",  
        "sep",  
        "vsep",
        "wrap",
        "vwrap",
        "attrs",
        "depth",
        "parent",
        "run_id",
        "model",
        "tool_calls",
        "usage",
        "id",
        "db_id",
        "event",
        "metadata",
    ]
    
    
    def __init__(
        self, 
        *chunks: ContentType | Chunk,
        children: list["Block"] | None = None,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        sep: str = " ",
        vsep: str = "\n",
        wrap: tuple[str, str] | None = None,
        vwrap: tuple[str, str] | None = None,
        attrs: dict | None = None,
        depth: int = 0,
        parent: "Block | None" = None,
        run_id: str | None = None,
        model: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        usage: LlmUsage | None = None,
        id: str | None = None,
        db_id: str | None = None,        
        event: StreamStatus | None = None,
        metadata: dict | None = None,
    ):
        """
        Basic component of prompt building. 
        """
        self.content: ChunkList = ChunkList([to_chunk(c) for c in chunks])
        self.children: "BlockList" = children_to_blocklist(children)
        self.role = role        
        self.tags: list[str] = tags or []
        self.styles = parse_style(style)
        self.attrs = attrs or {}
        self.depth = depth
        self.parent = parent
        self.run_id = run_id
        self.model = model
        self.tool_calls = tool_calls or []
        self.usage = usage
        self.id = id
        self.db_id = db_id
        self.sep = sep
        self.vsep = vsep
        self.wrap = wrap
        self.vwrap = vwrap
        self.event = event
        self.metadata = metadata
        
    @property
    def is_block(self) -> bool:
        return len(self.children) > 0
    
    @property
    def is_inline(self) -> bool:
        return len(self.children) == 0
    
    @property
    def is_empty_content(self) -> bool:
        return len(self.content) == 0
    
    def hstack(self, other: "Block") -> "Block":
        """
        Horizontaly stack two blocks
        b1 = Block("Hello")
        b2 = Block("World")
        b3 = b1.hstack(b2)
        
        >>> b3.render()
        "Hello World"        
        """
        return Block(
            *self.content,
            *other.content,
            children=self.children + other.children,
            role=self.role,
            tags=self.tags + other.tags,
        )
    
    def vstack(self, other: "Block") -> "Block":
        """
        Vertically stack two blocks
        b1 = Block("Hello")
        b2 = Block("World")
        b3 = b1.vstack(b2)
        
        >>> b3.render()
        "Hello\nWorld"
        """
        return Block(
            children=[self, other],
            role=self.role,
            tags=self.tags + other.tags,
        )
        
    def ihstack(self, other: "Block") -> "Block":
        """
        In-place horizontaly stack two blocks
        b1 = Block("Hello")
        b2 = Block("World")
        b1.ihstack(b2)
        
        >>> b1.render()
        "Hello World"
        """
        self.content.extend(other.content)
        self.children.extend(other.children)
        self.role = self.role or other.role
        self.tags = self.tags + other.tags
        return self
    
    
    def append(self, *content: ContentType | Chunk):
        self.content.extend([to_chunk(c) for c in content])
        
    def extend(self, *children: "Block"):
        self.children.extend(children_to_blocklist(children))
    
    
    def add_child(self, child: "Block"):
        child.parent = self
        child.depth = self.depth + 1
        self.children.append(child)
        return self
        
    def add_content(self, content: Chunk):
        self.content.append(content)
    
    
    def __enter__(self):
        return BlockContext(self)
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
        
    def __add__(self, other: "Block"):
        return self.hstack(other)
    
    def __radd__(self, other: "Block"):
        return other.hstack(self)
    
    def __iadd__(self, other: "Block"):
        self.ihstack(other)
        return self
    
    def render(self) -> str:
        return render(self)
    
    def print(self):
        print(self.render())
    
    def __str__(self) -> str:
        return self.render()
    
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize
            )
        )
        
    @staticmethod
    def _validate(v: Any) -> Any:
        if isinstance(v, Block):
            return v
        else:
            raise ValueError(f"Invalid block: {v}")

    @staticmethod
    def _serialize(v: Any) -> Any:
        if isinstance(v, Block):
            return v.model_dump()
        else:
            raise ValueError(f"Invalid block: {v}")
        
        
    def to_model(self) -> "BlockModel":
        from promptview.model.block_model import BlockModel
        return BlockModel.from_block(self)
    
    def model_dump(self):
        dump = {}
        for slot in self.__slots__:
            if hasattr(self, slot):
                dump[slot] = getattr(self, slot)
        return dump
    
        
        return {
            "_type": self.__class__.__name__,
            "content": self.content,
            "children": [c.model_dump() for c in self.children],
            "role": self.role,
            "tags": self.tags,
            "styles": self.styles,
            "attrs": self.attrs,
            "depth": self.depth,
            "parent": self.parent,
            "run_id": self.run_id,
            "model": self.model,
            "tool_calls": [tool.model_dump() for tool in self.tool_calls],
            "usage": self.usage.model_dump() if self.usage else None,
            "id": self.id,
            "db_id": self.db_id,
            "sep": self.sep,
            "event": self.event,
            "metadata": self.metadata,
        }
    
    
    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data:
            raise ValueError("Missing _type, not a valid block")
        if data["_type"] != cls.__name__:
            raise ValueError(f"Invalid _type: {data['_type']}")
        _type = data.pop("_type")
        children = data.pop("children")
        content = data.pop("content")
        content = content if isinstance(content, tuple) else (content,)
        return cls(*content,**data, children=[cls.model_validate(c) for c in children])



class BlockList(list[Block]):
    
    # def __init__(self, blocks: list[Block]):
    #     super().__init__(blocks)
    
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize
            )
        )
        
    @staticmethod
    def _validate(v: Any) -> Any:
        if isinstance(v, BlockList):
            return v
        elif isinstance(v, list):
            for item in v:
                if not isinstance(item, Block):
                    raise ValueError(f"Invalid block list: {v}")
            return BlockList(v)
        else:
            raise ValueError(f"Invalid block list: {v}")

    @staticmethod
    def _serialize(v: Any) -> Any:
        if isinstance(v, BlockList):
            return [item.model_dump() for item in v]
        else:
            raise ValueError(f"Invalid block list: {v}")
        
        
        




class BlockContext:
    
    def __init__(self, root: Block):
        self.ctx = ContextStack()
        self.ctx.push(root)
        
        
    @property
    def last(self) -> Block:
        if self.ctx.top.children:
            target = self.ctx.top.children[-1]
        else:
            target =self.ctx.top
        return target
    
    @property
    def top(self) -> Block:
        return self.ctx.top
    
    @property
    def root(self) -> Block:
        return self.ctx.root
    
    @property
    def content(self) -> ChunkList:
        return self.ctx.top.content
    
    @property
    def children(self) -> BlockList:
        return self.ctx.top.children
    
    
    def build_block(
        self, 
        content: ContentType | Chunk, 
        children: list[Block] | None = None
    ) -> Block:    
        return Block(
            *content,
            children=children,
            role=self.ctx.top.role,
            tags=self.ctx.top.tags,
        )
        
        
        
        

    # def __call__(
    #     self, 
    #     *content: ContentType | Chunk | Block | list,
    #     role: str | None = None,
    #     tags: list[str] | None = None,
    #     style: str | None = None,
    #     attrs: dict | None = None,        
    # ):
    #     if isinstance(content, Block):
    #         self.extend_children(content)
    #     elif isinstance(content, Chunk):
    #         self.extend_content(content)
    #     elif isinstance(content, tuple):
    #         self.extend_children(Block(*content, role=role, tags=tags, style=style, attrs=attrs))
    #     elif isinstance(content, str):
    #         self.extend_children(Block(content, role=role, tags=tags, style=style, attrs=attrs))
    #     else:
    #         raise ValueError(f"Invalid content type: {type(content)}")
    #     return self
    
    def __call__(
        self, 
        *content: ContentType | Chunk | Block | list,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: dict | None = None,        
    ):
        if content:
            if isinstance(content[0], Block):
                self.extend_children(content)
            elif isinstance(content[0], Chunk):
                self.extend_content(content)
            elif isinstance(content[0], list):
                self.extend_children(*[Block(c, role=role, tags=tags, style=style, attrs=attrs) for c in content[0]])
            elif isinstance(content, tuple):
                self.extend_children(Block(*content, role=role, tags=tags, style=style, attrs=attrs))
                # self.extend_content(*[to_chunk(c) for c in content])        
            elif isinstance(content, str):
                self.extend_children(Block(content, role=role, tags=tags, style=style, attrs=attrs))
            else:
                raise ValueError(f"Invalid content type: {type(content)}")
        else:
            self.extend_children(Block(role=role, tags=tags, style=style, attrs=attrs))
        return self
    
    def __enter__(self):
        """
        Enter a new block context.
        with Block("title") as b:
            with b("subtitle") as b:
                b /= "item 1"
                b /= "item 2"
        """
        if self.ctx.top.children:
            target_block = self.ctx.top.children[-1]
        else:
            raise ValueError("No children to extend")
        self.ctx.push(target_block)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        self.ctx.pop()
        
    def extend_content(self, *content: Chunk):        
        for c in content:
            self.last.add_content(c)
        
    def extend_children(self, *children: Block):
        for c in children:
            self.ctx.top.add_child(c)

    

    def __itruediv__(self, content: ContentType | tuple[ContentType, ...] | Block):
        """
        Add child to the current block as a new line.
        with Block("title") as b:
            b /= "item 1"
            b /= "item 2"
            
        >>> b.render()
        "title\n item 1\n item 2"
        """
        if isinstance(content, list):
            raise ValueError("Cannot use list as single line content")
        elif isinstance(content, tuple):
            self.extend_children(*[Block(*[to_chunk(c) for c in content])])
        elif isinstance(content, Block):
            self.extend_children(content)
        else:
            self.extend_children(Block(content))
        return self
    
    
    def __iadd__(self, other: ContentType | tuple[ContentType, ...]):
        """
        Add content to the current block. inline.
        with Block("title") as b:
            b += "item 1"
            b += "item 2"
            
        >>> b.render()
        "title item 1 item 2"
        """
        if isinstance(other, list):
            raise ValueError("Cannot use list as single line content")
        elif isinstance(other, tuple):
            self.extend_content(*[to_chunk(c) for c in other])
        else:
            self.extend_content(to_chunk(other))
        return self
    
    
    def render(self) -> str:
        return render(self.ctx.root)
    
    def print(self):
        print(self.render())
    
    def __str__(self) -> str:
        return self.render()
    
    
    



class Blockable(Protocol):
    def block(self) -> Block:
        ...









def block(
    *content: ContentType | Chunk | Block | list,
    role: str | None = None,
    tags: list[str] | None = None,
    style: str | None = None,
    attrs: dict | None = None,
    sep: str = " ",
    vsep: str = "\n",
    wrap: tuple[str, str] | None = None,
):
    return Block(
        *content,
        role=role,
        tags=tags,
        style=style,
        attrs=attrs,
        sep=sep,
        vsep=vsep,
        wrap=wrap,
    )