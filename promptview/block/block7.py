from collections import UserList
from typing import TYPE_CHECKING, Any, Callable, Generic, List, Protocol, Set, Type, TypeVar, TypedDict, Unpack
from pydantic_core import core_schema
from pydantic import BaseModel, GetCoreSchemaHandler
from promptview.block.types import ContentType
from promptview.block.util import LlmUsage, ToolCall
if TYPE_CHECKING:
    from promptview.model.block_model import BlockModel
    from promptview.model.model import SelectQuerySet





CHUNK_TYPE = TypeVar("CHUNK_TYPE", str, int, float, bool, None)

class Chunk:
    
    __slots__ = [
        "content",
        "logprob",
    ]
    
    def __init__(self, content: ContentType, logprob: float = 0):
        self.content: ContentType = content 
        self.logprob: float = logprob
        
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
    


class BlockParams(TypedDict, total=False):
    role: str | None
    tags: list[str] | None
    style: str | None
    sep: str
    vsep: str
    wrap: tuple[str, str] | None
    vwrap: tuple[str, str] | None
    attrs: dict | None
    depth: int
    parent: "BaseBlock | None"
    run_id: str | None
    model: str | None
    tool_calls: list[ToolCall] | None
    usage: LlmUsage | None
    id: str | None
    db_id: str | None
    styles: list[str] | None
    logprob: float | None
    
def all_slots(cls):
    slots = []
    for base in cls.__mro__:
        if '__slots__' in base.__dict__:
            slots.extend(base.__slots__)
    return slots

class BaseBlock:
    
    __slots__ = [
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
    "_logprob",
    ]
    
    def __init__(self, **kwargs: Unpack[BlockParams]):        
        self.role: str | None = kwargs.get("role")
        self.tags: list[str] | None = kwargs.get("tags")
        if kwargs.get("styles"):
            self.styles = kwargs.get("styles")
        else:
            self.styles: list[str] | None = parse_style(kwargs.get("style"))
        
        self.sep: str = kwargs.get("sep", " ")
        self.vsep: str = kwargs.get("vsep", "\n")
        self.wrap: tuple[str, str] | None = kwargs.get("wrap")
        self.vwrap: tuple[str, str] | None = kwargs.get("vwrap")
        self.attrs: dict | None = kwargs.get("attrs")
        
        self.attrs: dict | None = kwargs.get("attrs")
        self.depth: int = kwargs.get("depth", 0)
        self.parent: "BaseBlock | None" = kwargs.get("parent")
        self.run_id: str | None = kwargs.get("run_id")
        self.model: str | None = kwargs.get("model")
        self.tool_calls: list[ToolCall] | None = kwargs.get("tool_calls")
        self.usage: LlmUsage | None = kwargs.get("usage")
        self.id: str | None = kwargs.get("id")
        self.db_id: str | None = kwargs.get("db_id")
        self._logprob: float | None = kwargs.get("logprob")
        
    # @property
    # def is_end_of_line(self) -> bool:
    #     return self.sep == "\n"
        
    @property
    def logprob(self) -> float | None:
        return self._logprob
    
        
    def model_dump(self):
        dump = {}
        for slot in all_slots(type(self)):
            if slot == "parent":
                continue
            if hasattr(self, slot):
                value = getattr(self, slot)
                if value is None:
                    continue
                dump[slot] = value
        dump["_type"] = self.__class__.__name__
        return dump
    
    
    def model_dump_json(self):
        import json
        return json.dumps(self.model_dump())
    
    # @classmethod
    # def model_validate(cls, data: dict):
    #     if "_type" not in data:
    #         raise ValueError("Missing _type, not a valid block")
    #     if data["_type"] != cls.__name__:
    #         raise ValueError(f"Invalid _type: {data['_type']}")
    #     _type = data.pop("_type")
    #     content = content if isinstance(content, tuple) else (content,)
    #     return cls(*content,**data, children=[cls.model_validate(c) for c in children])
    
    
    def render(self) -> str:
        from promptview.block.block_renderer2 import render
        result = render(self)
        return result if result is not None else ""
    
    def print(self):
        print(self.render())
    
    def __str__(self) -> str:
        out = self.render()
        if out is None:
            return "None"
        return out
        

class Block(BaseBlock):
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
        run_id, model, tool_calls, usage, id, db_id, sep: Advanced/streaming options

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
        "is_end_of_line",
    ]
    
    
    def __init__(
        self, 
        content: ContentType | None = None,
        **kwargs: Unpack[BlockParams]
    ):
        """
        Basic component of prompt building. 
        """
        super().__init__(**kwargs)
        self.is_end_of_line = False
        if kwargs.get("is_end_of_line"):
            self.is_end_of_line = kwargs.get("is_end_of_line")        
        else:
            #! if content is a string, check if it ends with a newline
            if type(content) is str:
                if content.endswith("\n"):
                    content = content[:-1]            
                    self.sep = "\n"
                    self.is_end_of_line = True
        
        self.content: ContentType = content
        
    
        
            
    @property
    def is_block(self) -> bool:
        return len(self.children) > 0
    
    @property
    def is_inline(self) -> bool:
        return len(self.children) == 0
    
    # @property
    # def is_empty_content(self) -> bool:
    #     return len(self.content) == 0
    
    # def hstack(self, other: "Block") -> "Block":
    #     """
    #     Horizontaly stack two blocks
    #     b1 = Block("Hello")
    #     b2 = Block("World")
    #     b3 = b1.hstack(b2)
        
    #     >>> b3.render()
    #     "Hello World"        
    #     """
    #     return Block(
    #         *self.content,
    #         *other.content,
    #         children=self.children + other.children,
    #         role=self.role,
    #         tags=self.tags + other.tags,
    #     )
    
    # def vstack(self, other: "Block") -> "Block":
    #     """
    #     Vertically stack two blocks
    #     b1 = Block("Hello")
    #     b2 = Block("World")
    #     b3 = b1.vstack(b2)
        
    #     >>> b3.render()
    #     "Hello\nWorld"
    #     """
    #     return Block(
    #         children=[self, other],
    #         role=self.role,
    #         tags=self.tags + other.tags,
    #     )
        
    # def ihstack(self, other: "Block") -> "Block":
    #     """
    #     In-place horizontaly stack two blocks
    #     b1 = Block("Hello")
    #     b2 = Block("World")
    #     b1.ihstack(b2)
        
    #     >>> b1.render()
    #     "Hello World"
    #     """
    #     self.content.extend(other.content)
    #     self.children.extend(other.children)
    #     self.role = self.role or other.role
    #     self.tags = self.tags + other.tags
    #     return self
    
    
    # def append(self, *content: ContentType | Chunk):
    #     self.content.extend([to_chunk(c) for c in content])
        
    # def extend(self, *children: "Block"):
    #     self.children.extend(children_to_blocklist(children))
    
    
    # def add_child(self, child: "Block"):
    #     child.parent = self
    #     child.depth = self.depth + 1
    #     self.children.append(child)
    #     return self
        
    # def add_content(self, content: Chunk):
    #     self.content.append(content)
    
    
    def __enter__(self):
        parent = self.parent
        block = self if self.content is not None else None
        ctx = BlockContext(
            block,
            role=self.role,
            attrs=self.attrs,
            tags=self.tags,
            depth=self.depth,
            parent=parent,
            run_id=self.run_id,
            model=self.model,
            tool_calls=self.tool_calls,
            usage=self.usage,
            id=self.id,
            db_id=self.db_id,
            styles=self.styles,
            sep=self.sep,
            vsep=self.vsep,
            wrap=self.wrap,
            vwrap=self.vwrap,
        )
        self.parent = ctx
        if isinstance(parent, BlockContext):
            parent.children.pop()
            parent.append_child(ctx)
        return ctx
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
        
    def __add__(self, other: "Block"):
        
        
        return BlockList(
            [self, other], 
            role=self.role,
            attrs=self.attrs,
            depth=self.depth,
            parent=self.parent,
            run_id=self.run_id,
            model=self.model,
            tool_calls=self.tool_calls,
            usage=self.usage,
            id=self.id,
            db_id=self.db_id,
        )
    
    def __radd__(self, other: "Block"):
        return other.hstack(self)
    
    def __iadd__(self, other: "Block"):
        self.ihstack(other)
        return self
    
    def __eq__(self, other: object):
        if isinstance(other, str):
            return self.content == other
        elif isinstance(other, Block):
            return self.content == other.content
        else:
            return False
        
    
    
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
        dump = super().model_dump()
        dump["_type"] = "Block"
        dump["content"] = self.content        
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
        }
    
    
    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data or data["_type"] != "Block":
            raise ValueError(f"Invalid or missing _type for Block: {data.get('_type')}")
        data = dict(data)  # copy
        data.pop("_type")
        content = data.pop("content", None)
        children_data = data.pop("children", [])
        children = [Block.model_validate(child) for child in children_data]
        block = cls(content, **data)
        block.children = children
        return block



class BlockList(UserList[Block], BaseBlock):
    
    
    def __init__(self, blocks: list[Block] | None = None, **kwargs: Unpack[BlockParams]):
        if blocks is None:
            blocks = []
        for block in blocks:
            block.parent = self
        UserList.__init__(self, blocks)
        BaseBlock.__init__(self, **kwargs)        
    
    @property
    def logprob(self) -> float | None:
        return sum(block.logprob for block in self if block.logprob is not None)
    
    
    def model_dump(self):
        dump = super().model_dump()
        dump["_type"] = "BlockList"
        dump["blocks"] = [b.model_dump() for b in self]
        return dump
    
    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data or data["_type"] != "BlockList":
            raise ValueError(f"Invalid or missing _type for BlockList: {data.get('_type')}")
        data = dict(data)
        data.pop("_type")
        blocks_data = data.pop("blocks", [])
        blocks = [Block.model_validate(b) for b in blocks_data]
        return cls(blocks=blocks, **data)
    
    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: Any, handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize
            )
        )
        
    def get(self, tag: str):
        for block in self:
            if block.tags and tag in block.tags:
                return block
            elif isinstance(block, BlockContext):
                return block.get(tag)
        return None
        
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
        



def parse_content(content: ContentType | BaseBlock | list[str] | None = None, **kwargs: Unpack[BlockParams]) -> Block:
    if content is None:
        return Block(**kwargs)
    elif isinstance(content, Block):
        return content
    elif isinstance(content, list):
        return Block(content, **kwargs)
    elif isinstance(content, str):
        return Block(content, **kwargs)
    else:
        raise ValueError(f"Invalid content type: {type(content)}")
      
      
        
class BlockContext(BaseBlock):
    
    __slots__ = [
        "root",
        "children",
    ]
    
    def __init__(self, root: Block | BlockList | None = None, children: BlockList | None = None, **kwargs: Unpack[BlockParams]):
        super().__init__(**kwargs)
        if isinstance(root, Block):
            self.root: BlockList = BlockList([root], parent=self)
        elif isinstance(root, BlockList):
            self.root: BlockList = root
        else:
            self.root: BlockList = BlockList([], parent=self)
        if children is None:
            # self.children: BlockList = BlockList([], style="list-col", parent=self)
            self.children: BlockList = BlockList([], parent=self)
        else:
            self.children: BlockList = children
            # if self.children.styles:    
            #     self.children.styles.append("list-col")
            # else:
            #     self.children.styles = ["list-col"]
        # self.styles = ["list-col"] + (self.styles or [])
        # if root:
            # root.parent = self
    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data or data["_type"] != "BlockContext":
            raise ValueError(f"Invalid or missing _type for BlockContext: {data.get('_type')}")
        data = dict(data)
        data.pop("_type")
        root_data = data.pop("root", None)
        children_data = data.pop("children", [])
        root = BlockList.model_validate(root_data) if root_data else BlockList()
        children = BlockList.model_validate({"_type": "BlockList", "blocks": children_data}) if children_data else BlockList()
        return cls(root=root, children=children, **data)
    
    @property
    def logprob(self) -> float | None:
        logprob = sum(block.logprob for block in self.children if block.logprob is not None) or 0
        root_logprob = self.root.logprob or 0
        return logprob + root_logprob
       
    def field(self, name: str, type: Type):
        block = FieldBlock(name, type)
        self.append_child(block)
        return block
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
            
            
    # def __call__(self, content: ContentType | BaseBlock | list[str] | None = None) -> Block:
    #     if content is None:
    #         content = Block()
            
    #     if isinstance(content, Block):
    #         self.append_child(content)
    #         return content
    #     elif isinstance(content, list):
    #         for c in content:
    #             self.append_child(c)
    #         return c
    #     else:
    #         content = Block(content)
    #         self.append_child(content)
    #         return content
    
    def __call__(self, content: ContentType | BaseBlock | list[str] | None = None, **kwargs: Unpack[BlockParams]) -> Block:
        # if isinstance(content, str)
        block = parse_content(content, **kwargs)
        self.append_child(block)
        return block
    
    
    def __iadd__(self, other: ContentType | Block | tuple[ContentType, ...]):
        if isinstance(other, ContentType):            
            other = Block(other)        
            self.append_root(other)
        elif isinstance(other, Block):
            self.append_child(other, as_line=True)
        elif isinstance(other, tuple):
            for c in other:
                if isinstance(c, ContentType):
                    c = Block(c)
                self.append_root(c)
        else:
            raise ValueError(f"Invalid content type: {type(other)}")
        return self
    
    
    def __itruediv__(self, other: ContentType | Block | tuple[ContentType, ...]):
        if not isinstance(other, Block):
            if isinstance(other, tuple):
                other = BlockList([Block(item) for item in other], style="list:row")                
            else:
                other = Block(other)
        
        self.append_child(other)
        return self
    
    
    
    def append_child(self, child: Block, as_line: bool = False):
        child.parent = self
        if as_line:
            if not self.children or not isinstance(self.children[-1], BlockList):
                self.children.append(BlockList([]))
            self.children[-1].append(child)
            if child.is_end_of_line:
                self.children.append(BlockList([]))
        else:
            self.children.append(child)        
        return self
    
    def append_root(self, content: ContentType | Block):
        if not isinstance(content, Block):
            content = Block(content)
        content.parent = self
        self.root.append(content)
        return self
    
    
    def response_schema(self, name: str | None = None):
        name = name or "response_schema"
        block = BlockSchema(name=name)
        self.append_child(block)
        return block
    
    
    def get(self, tag: str):
        tag = tag.lower()
        for child in self.children:
            if child.tags and tag in child.tags:
                return child
            elif isinstance(child, BlockContext):
                block = child.get(tag)
                if block:
                    return block
        return None

    def get_field(self):
        for child in self.children:
            if isinstance(child, FieldBlock):
                return child
            elif isinstance(child, BlockContext):
                for b in child.root:
                    if isinstance(b, FieldBlock):
                        return b
        return None
    
    def model_dump(self):
        dump = super().model_dump()
        # dump = self.base_model_dump()
        dump["_type"] = "BlockContext"
        dump["root"] = self.root.model_dump()
        dump["children"] = [c.model_dump() for c in self.children]
        return dump
    
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
        if isinstance(v, BlockContext):
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
        if isinstance(v, BlockContext):
            return v.model_dump()
        else:
            raise ValueError(f"Invalid block list: {v}")
        
        
        
    def reduce_tree(self, is_target: Callable[[BaseBlock], bool] | None = None, clone_target_node = None) -> "ResponseContext":
        """Return a forest containing only target-type nodes, attached under their
        nearest target-type ancestor from the original tree."""
        dummy_children: List[BaseBlock] = []
        stack: List[BlockContext] = []  # stack of cloned target nodes
        
        def _clone_target_node(n: BlockContext) -> ResponseContext:
            # Copy only what you need; children will be filled during reduction.
            for b in n.root:
                if isinstance(b, FieldBlock):
                    return ResponseContext(b)
            raise ValueError("No field block found")
        
        def _is_target(node: BaseBlock) -> bool:
            if isinstance(node, FieldBlock):
                return True
            elif isinstance(node, BlockContext):
                for b in node.root:
                    if isinstance(b, FieldBlock):
                        return True
            return False
        
        is_target = is_target or _is_target
        clone_target_node = clone_target_node or _clone_target_node

        def dfs(u: BlockContext):
            created = None
            if is_target(u):
                created = clone_target_node(u)
                if stack:
                    stack[-1].children.append(created)
                else:
                    dummy_children.append(created)
                stack.append(created)

            if isinstance(u, BlockContext):
                for child in u.children:
                    dfs(child)
                    
            if created is not None:
                stack.pop()

        dfs(self)
        if not dummy_children:
            raise ValueError("No target nodes found")
        return dummy_children[0]
        
    def __repr__(self) -> str:
        root = self.root.render() if self.root else ''
        tags = ','.join(self.tags) if self.tags else ''
        tags = f"[{tags}] " if tags else ''
        return f"BlockContext({tags}root={root}, children={self.children})"



class FieldBlock(Block):
    
    def __init__(self, name: str, type: Type):
        super().__init__(name, tags=[name], style="xml")
        self.type = type
        self.name = name
        
        
    # def __enter__(self):
    #     parent = self.parent
    #     block = self if self.content is not None else None
    #     ctx = FieldContext(
    #         block,
    #         role=self.role,
    #         attrs=self.attrs,
    #         tags=self.tags,
    #         depth=self.depth,
    #         parent=parent,
    #         run_id=self.run_id,
    #         model=self.model,
    #         tool_calls=self.tool_calls,
    #         usage=self.usage,
    #         id=self.id,
    #         db_id=self.db_id,
    #         styles=self.styles,
    #         sep=self.sep,
    #         vsep=self.vsep,
    #         wrap=self.wrap,
    #         vwrap=self.vwrap,
    #     )
    #     self.parent = ctx
    #     if isinstance(parent, BlockContext):
    #         parent.children.pop()
    #         parent.append_child(ctx)
    #     return ctx




class FieldContext(BlockContext):
    pass



class ResponseContext(BlockContext):
    
    def __init__(self, schema: FieldBlock, children: BlockList | None = None, **kwargs: Unpack[BlockParams]):
        super().__init__(children=children, tags=[schema.name], **kwargs)
        self.schema = schema
    
    @property
    def name(self) -> str:
        return self.schema.name
    
    
    def __repr__(self) -> str:
        root = self.root.render() if self.root else ''
        tags = ','.join(self.tags) if self.tags else ''
        tags = f"[{tags}] " if tags else ''
        return f"ResponseContext({tags}root={root}, children={self.children})"
    
    
    


class ResponseBlock(Block):
    
    def __init__(self, schema: FieldBlock):
        self.schema = schema
        super().__init__(role="assistant", tags=[schema.name])
        
        
    

class BlockSchema(Block):
      
    def __init__(self, name: str = "schema"):
        super().__init__(tags=[name])




    
    # def __
    
# class ResponseBlock(Block):
    
#     def __init__(self, content: str):
#         self.
    
    
#     def append(self, content: str):


class BlockPrompt:
    
    def __init__(self):
        self.ctx = ContextStack()
        self._root = BlockList()        
        
        
        
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
    #     if content:
    #         if isinstance(content[0], Block):
    #             self.extend_children(content)
    #         elif isinstance(content[0], Chunk):
    #             self.extend_content(content)
    #         elif isinstance(content[0], list):
    #             self.extend_children(*[Block(c, role=role, tags=tags, style=style, attrs=attrs) for c in content[0]])
    #         elif isinstance(content, tuple):
    #             self.extend_children(Block(*content, role=role, tags=tags, style=style, attrs=attrs))
    #             # self.extend_content(*[to_chunk(c) for c in content])        
    #         elif isinstance(content, str):
    #             self.extend_children(Block(content, role=role, tags=tags, style=style, attrs=attrs))
    #         else:
    #             raise ValueError(f"Invalid content type: {type(content)}")
    #     else:
    #         self.extend_children(Block(role=role, tags=tags, style=style, attrs=attrs))
    #     return self
    
    def __call__(self, content: ContentType | BaseBlock | list[str] | None = None, **kwargs: Unpack[BlockParams]) -> Block:
        block = parse_content(content, **kwargs)
        # self._root.append(block)
        self.ctx.push(block)
        return block
    
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
        from promptview.block.block_renderer2 import render
        result = render(self.ctx.root)
        return result if result is not None else ""
    
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