



from typing import Any, Generic, List, Set, TypeVar

from promptview.block.block_renderer2 import render





ContentType = str | int | float | bool | None

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


class Block:
    
    __slots__ = [
        "content",
        "children",
        "role",        
        "tags",
        "styles",        
        "attrs",
        "depth",
        "parent",
    ]
    
    
    def __init__(
        self, 
        *chunks: ContentType | Chunk,
        children: list["Block"] | None = None,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: dict | None = None,
        depth: int = 0,
        parent: "Block | None" = None,
    ):
        self.content: ChunkList = ChunkList([to_chunk(c) for c in chunks])
        self.children: "BlockList" = children_to_blocklist(children)
        self.role = role        
        self.tags: list[str] = tags or []
        self.styles = parse_style(style)
        self.attrs = attrs or {}
        self.depth = depth
        self.parent = parent
        
    @property
    def is_block(self) -> bool:
        return len(self.children) > 0
    
    @property
    def is_inline(self) -> bool:
        return len(self.children) == 0
    
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


class BlockList(list[Block]):
    
    def __init__(self, blocks: list[Block]):
        super().__init__(blocks)
        
        
        
        




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
    
    def __call__(
        self, 
        *content: ContentType | Chunk | Block,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | List[str] | None = None,
        attrs: dict | None = None,        
    ):
        if isinstance(content, Block):
            self.extend_children(content)
        elif isinstance(content, Chunk):
            self.extend_content(content)
        elif isinstance(content, tuple):
            self.extend_children(Block(*content, role=role, tags=tags, style=style, attrs=attrs))
        elif isinstance(content, str):
            self.extend_children(Block(content, role=role, tags=tags, style=style, attrs=attrs))
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
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
    
    
    
    
    
    