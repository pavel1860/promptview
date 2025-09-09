import textwrap
from typing import Callable, List, Type
from .base_blocks import BaseBlock, BaseContent, BlockSequence
import annotated_types



def parse_style(style: str | List[str] | None) -> List[str]:
    if isinstance(style, str):
        return list(style.split(" "))
    elif type(style) is list:
        return style
    else:
        return []


class BlockChunk(BaseBlock[str]):
    
    __slots__ = [
        "logprob",
        "type",
    ]
    
    def __init__(self, content: str, logprob: float | None = None, prefix: str | None = None, postfix: str | None = None):
        super().__init__(content, prefix=prefix, postfix=postfix)
        self.logprob: float | None = logprob
        self.type: Type = type(content)
        
        
    @property
    def is_eol(self) -> bool:
        if self.type is str and self.content is not None:
            return self.content.endswith("\n")
        return False
    
    def __repr__(self):
        return f"BlockChunk(content={self.content}, logprob={self.logprob})"



class BlockSent(BlockSequence[BlockChunk]):
    
    
    def promote_content(self, content: BaseContent, prefix: str | None = None, postfix: str | None = None) -> BlockChunk:
        if isinstance(content, str):
            return BlockChunk(content, prefix=prefix, postfix=postfix)
        elif isinstance(content, int):
            return BlockChunk(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, float):
            return BlockChunk(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, bool):
            return BlockChunk(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, BlockSent):
            raise ValueError("Cannot promote BlockSent to BlockChunk")
        elif isinstance(content, BlockChunk):
            return content
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
        
    @property
    def logprob(self) -> float | None:
        logprob = sum(blk.logprob for blk in self.children if blk.logprob is not None) or 0
        return logprob
    
    
    def is_last_eol(self) -> bool:
        if len(self) == 0:
            return True
        return self.children[-1].is_eol
    
    
    def render(self, verbose: bool = False) -> str:
        from .renderers import render
        return render(self)
    
    def print(self, verbose: bool = False):
        print(self.render(verbose=verbose))
    
BlockContent = BlockSent | BlockChunk | BaseContent 
 

class Block(BlockSequence["Block"]):
    
    __slots__ = [
        "root",
        "role",
        "tags",
        "styles",
        "attrs",
        "default_sep",
        "postfix",
        "prefix",
    ]
    
    def __init__(
        self, 
        root: BlockContent | None = None,
        children: list["Block"] | None = None,
        *,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        styles: list[str] | None = None,
        attrs: dict[str, str] | None = None,
        default_sep: str = "\n",
        prefix: BaseContent | None = None,
        postfix: BaseContent | None = None,
        parent: "Block | None" = None,
    ):
        super().__init__(children=children, default_sep=default_sep, parent=parent)
        self.role: str | None = role
        self.tags: list[str] = tags or []
        self.styles: list[str] = styles or parse_style(style)
        self.attrs: dict[str, str] = attrs or {}
        self.default_sep: str = default_sep
        if root is None:
            self.root = BlockSent(parent=self)
        elif isinstance(root, BlockSent):
            self.root = root
        else:
            self.root = BlockSent(parent=self)
            self.root.append(root)
        self.postfix = postfix
        self.prefix = prefix
        
        
    def promote_content(self, content: "Block | BlockSent | BaseContent", prefix: BaseContent | None = None, postfix: BaseContent | None = None) -> "Block":
        if isinstance(content, str):
            return Block(content, prefix=prefix, postfix=postfix)
        elif isinstance(content, int):
            return Block(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, float):
            return Block(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, bool):
            return Block(str(content), prefix=prefix, postfix=postfix)
        elif isinstance(content, Block):
            return content
        elif isinstance(content, BlockSent):
            return Block(content, prefix=prefix, postfix=postfix)
        elif isinstance(content, BlockChunk):
            return Block(content, prefix=prefix, postfix=postfix)        
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
        
    @property
    def logprob(self) -> float | None:
        logprob = sum(blk.logprob for blk in self.children if blk.logprob is not None) or 0
        if self.root is not None:
            logprob += self.root.logprob or 0
        if self.postfix is not None:
            logprob += self.postfix.logprob or 0
        if self.prefix is not None:
            logprob += self.prefix.logprob or 0
        return logprob

    
    
    def view(self, name: str, type: Type, attrs: dict[str, str] | None = None, tags: list[str] | None = None) -> "BlockSchemaField":
        # block = FieldBlock(name, type, attrs=attrs)
        block = BlockSchema(
            name,
            type=type,
            attrs=attrs,
            role=self.role,
            parent=self.parent,
            tags=tags,
            styles=["xml"],
        )
        self.append(block)
        return block
    
    def attr(
        self, 
        name: str,
        type: Type, 
        description: str,
        gt: int | float | None = None,
        lt: int | float | None = None,
        ge: int | float | None = None,
        le: int | float | None = None,
    ) -> "None":
        if gt is not None: annotated_types.Gt(gt)
        if lt is not None: annotated_types.Lt(lt)
        if ge is not None: annotated_types.Ge(ge)
        if le is not None: annotated_types.Le(le)
        self.attrs[name] = FieldAttrBlock(
            name=name,
            type=type,
            description=description,
            gt=gt,
            lt=lt,
            ge=ge,
            le=le,
        )
        
    def get(self, tag: str):
        tag = tag.lower()
        if tag in self.tags:
            return self
        for child in self.children:
            if isinstance(child,Block):
                if tag in child.tags:
                    return child                            
                if (block:= child.get(tag)) is not None:
                    return block
        return None

        
    def _should_add_sentence(self):
        if not len(self):
            return True
        if not isinstance(self.last, BlockSent):
            return True
        if self.children[-1].is_last_eol:
            return True
        return False
    
    def is_last_eol(self) -> bool:
        if len(self.children) == 0:
            return True
        return self.children[-1].root.is_last_eol  

    
    def inline_append(self, content: "Block | BlockSent | BaseContent", sep: str = " "):        
        if isinstance(content, Block):
            self.append(content, sep=sep)
            return self.children[-1]
        elif isinstance(content, BlockSent):
            block = Block(root=content)
            self.append(block, sep=sep)
            return self.children[-1]
        else:
            if self.is_last_eol():
                self.append(content, sep=sep)
                return self.children[-1]
            else:
                last = self.children[-1]
                if last.root.is_last_eol:
                    self.append(content, sep=sep)
                    return self.children[-1]
                else:
                    last.root.append(content, sep=sep)
                    return last.root.children[-1]



    def gather_trees(self, is_target: Callable[[BaseBlock], bool] | None = None, clone_target_node = None) -> "list[BaseBlock]":
        """Return a forest containing only target-type nodes, attached under their
        nearest target-type ancestor from the original tree."""
        dummy_children: List[BaseBlock] = []
        stack: List[Block] = []  # stack of cloned target nodes

        def dfs(u: Block):
            created = None
            if is_target(u):
                created = clone_target_node(u)
                if stack:
                    stack[-1].append(created)
                else:
                    dummy_children.append(created)
                stack.append(created)

            if isinstance(u, Block):
                for child in u.children:
                    dfs(child)
                    
            if created is not None:
                stack.pop()

        dfs(self)
        if not dummy_children:
            raise ValueError("No target nodes found")
        # res = Block(children=BlockList(dummy_children))
        return dummy_children

    
    def model_dump(self):
        dump = super().model_dump()
        dump["_type"] = "Block"
        dump["root"] = self.root.model_dump()
        dump["children"] = [c.model_dump() for c in self.children]
        dump["styles"] = self.styles
        dump["tags"] = self.tags
        dump["attrs"] = self.attrs
        dump["role"] = self.role
        dump["id"] = self.id
        dump["path"] = self.path
        dump["prefix"] = self.prefix
        dump["postfix"] = self.postfix
        return dump
    
    
    
    def __enter__(self):        
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    
    
    def __call__(
        self, 
        content: BaseContent | BaseBlock | list[str] | None = None, 
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: "dict[str, FieldAttrBlock] | None" = None,
    ) -> "Block":        
        block = Block(
            content,
            role=role,
            tags=tags,            
            parent=self,            
            style=style,
            attrs=attrs,
        )      
        self.append(block)
        return block
    
    
    def _process_tuple_content(self, other: tuple[BaseContent, ...]):
        block = BlockSent(default_sep=" ")
        for o in other:
            block.append(o)
        return block
        
    
    
    def __iadd__(self, other: BaseContent | BlockSent | tuple[BaseContent, ...]):
        if isinstance(other, tuple):
            for o in other:
                self.root.append(o)
        else:
            self.root.append(other)
        return self
    
    def __iand__(self, other: BaseContent | BlockSent | BlockChunk | tuple[BaseContent, ...]):
        if isinstance(other, tuple):
            for o in other:
                self.root.append(o, sep="")
        else:
            self.root.append(other, sep="")
        return self
            
    
    
    def __itruediv__(self, other: "BaseContent | BlockChunk | Block | BlockSent | tuple[BaseContent, ...]"):        
        if isinstance(other, tuple):
            other =self._process_tuple_content(other)        
        self.append(other)
        return self
    
        
    def __repr__(self) -> str:
        root = self.root.render() if self.root else ''
        tags = ','.join(self.tags) if self.tags else ''
        tags = f"[{tags}] " if tags else ''
        return f"{self.__class__.__name__}({tags}root={root}, children={self.children})"


    def render(self, verbose: bool = False) -> str:
        from .renderers import render
        return render(self)

    def print(self, verbose: bool = False):
        print(self.render(verbose=verbose))

def FieldAttr(
    type: Type,
    description: str,
    name: str | None = None,
    gt: annotated_types.Gt | None = None,
    lt: annotated_types.Lt | None = None,
    ge: annotated_types.Ge | None = None,
    le: annotated_types.Le | None = None,
):
    return FieldAttrBlock(
        name=name,
        type=type,
        description=description,
        gt=gt,
        lt=lt,
        ge=ge,
        le=le,
    )


class FieldAttrBlock:
    name: str
    type: Type = str
    description: str
    gt: annotated_types.Gt | None = None
    lt: annotated_types.Lt | None = None
    ge: annotated_types.Ge | None = None
    le: annotated_types.Le | None = None
    
    def __init__(
        self, 
        name: str,          
        description: str, 
        type: Type = str,
        gt: annotated_types.Gt | None = None, 
        lt: annotated_types.Lt | None = None, 
        ge: annotated_types.Ge | None = None, 
        le: annotated_types.Le | None = None
    ):
        self.name = name
        self.type = type
        self.description = description
        self.gt = gt
        self.lt = lt
        self.ge = ge
        self.le = le
        
        
    def parse(self, content: str):
        content = content.strip()
        content = textwrap.dedent(content)
        if self.type == int:
            return int(content)
        elif self.type == float:
            return float(content)
        elif self.type == bool:
            return bool(content)
        elif self.type == str:
            return content
        elif self.type == list:
            return content.split(",")
        elif self.type == dict:
            return json.loads(content)
        else:
            raise ValueError(f"Invalid type: {self.type}")






class BlockSchema(Block):
    
    __slots__ = [
        "type",
        "name",
    ]
    
    def __init__(
        self, 
        name: str,
        type: Type,
        attrs: dict[str, FieldAttrBlock] | None = None,        
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        id: str | None = None,
        index: int | None = None,
        parent: "BaseBlock | None" = None,  
        styles: list[str] | None = None,
    ):
        super().__init__(name, tags=tags or [] + [name], style=style, parent=parent, attrs=attrs, styles=styles)
        if not type:
            raise ValueError("type is required")
        self.type = type
        self.name = name
        
        
    def copy(
        self,
        children: list["Block"] | None = None,
        name: str | None = None,
        type: Type | None = None,
        attrs: dict[str, FieldAttrBlock] | None = None,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        id: str | None = None,
        index: int | None = None,
        parent: "BaseBlock | None" = None,
        styles: list[str] | None = None,
    ):
        return BlockSchema(
            name=self.name if name is None else name,
            type=self.type if type is None else type,
            attrs=self.attrs if attrs is None else attrs,
            role=self.role if role is None else role,
            tags=self.tags if tags is None else tags,
            style=self.style if style is None else style,
            id=self.id if id is None else id,
            index=self.index if index is None else index,
            parent=self.parent if parent is None else parent,
            styles=self.styles if styles is None else styles,
        )
