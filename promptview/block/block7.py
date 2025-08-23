from collections import UserList
import copy
import json
import textwrap
from typing import TYPE_CHECKING, Annotated, Any, Callable, Generic, List, Protocol, Sequence, Set, Type, TypeVar, TypedDict, Unpack
import annotated_types
from pydantic_core import core_schema
from pydantic import BaseModel, GetCoreSchemaHandler
from promptview.block.types import ContentType
from promptview.block.util import LlmUsage, ToolCall
if TYPE_CHECKING:
    from promptview.model.block_model import BlockModel
    from promptview.model.model import SelectQuerySet





CHUNK_TYPE = TypeVar("CHUNK_TYPE", str, int, float, bool, None)




class ContextStack:
    """
    A stack-based context for managing nested block structures.
    """
    _ctx_stack: "list[BlockChunk]"
    
    def __init__(self):
        self._ctx_stack = []
        
        
    @property
    def top(self):
        return self._ctx_stack[-1]
    
    @property
    def root(self) -> "BlockChunk":
        if not self._ctx_stack:
            raise ValueError("No context stack")
        return self._ctx_stack[0]
        
    def __getitem__(self, idx: int) -> "BlockChunk":
        return self._ctx_stack[idx]
    
    def __len__(self) -> int:
        return len(self._ctx_stack)
    
    
    
    def push(self, block: "BlockChunk"):
        self._ctx_stack.append(block)
        
    def pop(self):
        return self._ctx_stack.pop()
    


def children_to_blocklist(children: list["BlockChunk"] | tuple["BlockChunk", ...] | None) -> "BlockList":
    if children is None:
        return BlockList([])
    if isinstance(children, BlockList):
        return children
    return BlockList(list(children))


def parse_style(style: str | List[str] | None) -> List[str]:
    if isinstance(style, str):
        return list(style.split(" "))
    elif type(style) is list:
        return style
    else:
        return []



class BaseBlockParams(TypedDict, total=False):
    index: int | None
    parent: "BaseBlock | None"

class BlockChunkParams(BaseBlockParams):
    content: ContentType | None
    sep: str
    logprob: float | None
    is_end_of_line: bool


class BlockParams(BaseBlockParams):
    role: str | None
    tags: list[str] | None
    style: str | None
    attrs: dict[str, "str | FieldAttrBlock"] | None     
    id: str | None
    styles: list[str] | None
    
    
class FieldBlockParams(BlockParams):
    type: Type
    attrs: dict[str, "str | FieldAttrBlock"] | None
    
def all_slots(cls):
    slots = []
    for base in cls.__mro__:
        if '__slots__' in base.__dict__:
            slots.extend(base.__slots__)
    return slots



def get_attrs(attrs: dict[str, "str | FieldAttrBlock"] | None) -> "dict[str, FieldAttrBlock]":
    if attrs is None:
        return {}
    return {k: v if isinstance(v, FieldAttrBlock) else FieldAttrBlock(name=k, description=v) for k, v in attrs.items()}

class BaseBlock:
    
    __slots__ = [
        "id",
        "parent",
        "index",
    ]
    
    
    def __init__(
        self, 
        index: int | None = None, 
        parent: "BaseBlock | None" = None,
        id: str | None = None,
    ):
        self.index = index or 1
        self.parent = parent
        self.id = id
    
    @property
    def path(self) -> list[int]:
        raise NotImplementedError("Not implemented")

    
    @property
    def block_parent(self):
        if isinstance(self.parent, BlockList):
            return self.parent.parent
        return self.parent       

    
        
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
    

    
    def render(self, verbose: bool = False) -> str:
        from promptview.block.block_renderer2 import render
        result = render(self, verbose=verbose)
        return result if result is not None else ""
    
    def print(self, verbose: bool = False):
        print(self.render(verbose=verbose))
    
    def __str__(self) -> str:
        out = self.render()
        if out is None:
            return "None"
        return out
        

class BlockChunk(BaseBlock):
    
    __slots__ = [
        "content",
        "children",
        "logprob",
    ]
    
    
    def __init__(
        self, 
        content: ContentType | None = None,
        logprob: float | None = None,
        parent: "BaseBlock | None" = None,        
        index: int | None = None,
        id: str | None = None,
    ):
        """
        Basic component of prompt building. 
        """
        super().__init__(parent=parent, id=id, index=index)
        self.content: ContentType = content        
        self.logprob: float | None = logprob
        # self.is_end_of_line = False
        # if is_end_of_line:
        #     self.is_end_of_line = is_end_of_line        
        # else:
        #     #! if content is a string, check if it ends with a newline
        #     if self._detect_end_of_line(content):
        #         self.sep = "\n"
        #         self.is_end_of_line = True
        
    @property
    def is_eol(self) -> bool:
        if isinstance(self.content, str):
            return self.content.endswith("\n")
        return True
        
    
    def _detect_end_of_line(self, content: ContentType):
        if type(content) is str:
            if content.endswith("\n"):
                content = content[:-1]            
                return True
        return False
    
    def copy(self, with_parent: bool = True):
        if with_parent:
            return BlockChunk(self.content, logprob=self.logprob, parent=self.parent, index=self.index, id=self.id)
        else:
            return BlockChunk(self.content, logprob=self.logprob, index=self.index, id=self.id)
    
    def replace(self, old: str, new: str):
        if isinstance(self.content, str):
            self.content = self.content.replace(old, new)
        else:
            raise ValueError(f"Cannot replace content of type {type(self.content)}")
        return self
                 
    def __getitem__(self, key):
        if isinstance(key, slice) and isinstance(self.content, str):
            # Special-case for "[:-1]"
            if key.start is None and key.stop == -1 and key.step is None:
                return self.content[:-1]
            # Otherwise, fall back to normal slicing
            return self.content[key]
        else:
            # Normal indexing
            if isinstance(self.content, str):
                return self.content[key]
            else:
                raise ValueError(f"Cannot index content of type {type(self.content)}")
    
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
        
    def __add__(self, other: "BlockChunk"):
        
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
    
    def __radd__(self, other: "BlockChunk"):
        return other.hstack(self)
    
    def __iadd__(self, other: "BlockChunk"):
        self.ihstack(other)
        return self
    
    def __eq__(self, other: object):
        if isinstance(other, str):
            return self.content == other
        elif isinstance(other, BlockChunk):
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
        if isinstance(v, BlockChunk):
            return v
        else:
            raise ValueError(f"Invalid block: {v}")

    @staticmethod
    def _serialize(v: Any) -> Any:
        if isinstance(v, BlockChunk):
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
        children = [BlockChunk.model_validate(child) for child in children_data]
        block = cls(content, **data)
        block.children = children
        return block
    
    
    def __str__(self):
        if isinstance(self.content, str):
            return self.content
        else:
            return str(self.content)
    
    def __repr__(self):
        return f"BlockChunk(content={self.content}, logprob={self.logprob})"



class BlockSent(UserList[BlockChunk], BaseBlock):
    
    __slots__ = [
        "sep_list",
        "has_eol",
    ]
    
    
    def __init__(
        self, 
        chunks: list[BlockChunk] | None = None, 
        sep: str = " ", 
        wrap: tuple[str, str] | None = None,
        index: int | None = None,
        parent: "BaseBlock | None" = None,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: "dict[str, FieldAttrBlock] | None" = None,
        id: str | None = None,
        styles: list[str] | None = None,
    ):
        if chunks is None:
            chunks = []
    
        UserList.__init__(self, chunks)
        BaseBlock.__init__(self, parent=parent, index=index)
        self.sep_list = []
        self.default_sep = sep
        for chunk in chunks:
            if not hasattr(chunk, "is_eol"):
                print(f"Warning: {chunk} is not a BlockChunk")                
            if chunk.is_eol:
                if self.has_eol:
                    raise ValueError("Cannot append to a list that has an end of line")
                sep = ""
                self.has_eol = True
                chunk = chunk.replace("\n", "")
            self.sep_list.append(sep)

            
        self.has_eol = False
        if wrap:
            self.wrap(*wrap)
            
    # @property
    # def path(self) -> list[int]:
    #     if self.parent is None:
    #         return [self.index]
    #     return self.parent.path + [self.index]
    
    @property
    def path(self) -> list[int]:
        if self.parent is None:
            return [self.index]
        if isinstance(self.parent, Block):
            return self.parent.path
        else:
            return self.parent.path + [self.index]
        
        

        
    @property
    def logprob(self) -> float | None:
        return sum(block.logprob for block in self if block.logprob is not None)
    
    
    def wrap(self, start_token: str, end_token: str):
        self.prepend(start_token)
        self.append(end_token)
    
    def _process_content(self, content: ContentType | BlockChunk):
        if isinstance(content, BlockChunk):
            return content
        elif isinstance(content, str):
            return BlockChunk(content)
        elif isinstance(content, int):
            return BlockChunk(content)
        elif isinstance(content, float):
            return BlockChunk(content)
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
    
    
    def append(self, content: ContentType | BlockChunk, sep: str | None = None):

        chunk = self._process_content(content)
        sep = sep or self.default_sep
        if chunk.is_eol:
            if self.has_eol:
                raise ValueError("Cannot append to a list that has an end of line")
            sep = ""
            self.has_eol = True
            chunk = chunk.replace("\n", "")
        self.sep_list.append(sep)
        UserList.append(self, chunk)
        
    def prepend(self, content: ContentType | BlockChunk, sep: str | None = None):
        self.insert(0, content, sep=sep)
        
    def insert(self, index: int, content: ContentType | BlockChunk, sep: str | None = None):
        if self.has_eol and index == len(self):
            raise ValueError("Cannot insert to the end of a list that has an end of line")
        block = self._process_content(content)
        sep = sep or self.default_sep
        if block.is_eol:
            if index != len(self):
                raise ValueError("end of line cannot be inserted in the middle of a list")
            if self.has_eol:
                raise ValueError("Cannot insert an end of line to a list that has an end of line")
            sep = "\n"
            self.has_eol = True
        self.sep_list.insert(index, sep)
        UserList.insert(self, index, block)
        
        
    def iter_chunks(self):
        if len(self) != len(self.sep_list):
            raise ValueError("Number of chunks and separators must match")
        for chunk, sep in zip(self, self.sep_list):
            yield chunk, sep
        
        
    def __add__(self, other: ContentType):
        self.append(other)
        return self
    
    def __and__(self, other: ContentType):
        self.append(other, sep="")
        return self
    
    def __iadd__(self, other: ContentType):
        self.append(other)
        return self
    
    def __radd__(self, other: ContentType):
        self.append(other)
        return self
    
    def __iradd__(self, other: ContentType):
        self.append(other)
        return self
    
        
        
    
    def model_dump(self):
        dump = super().model_dump()
        dump["_type"] = "BlockSent"
        dump["blocks"] = [b.model_dump() for b in self]
        return dump
    

    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data or data["_type"] != "BlockList":
            raise ValueError(f"Invalid or missing _type for BlockList: {data.get('_type')}")
        data = dict(data)
        data.pop("_type")
        blocks_data = data.pop("blocks", [])
        blocks = [BlockChunk.model_validate(b) for b in blocks_data]
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
            elif isinstance(block, Block):
                return block.get(tag)
        return None
        
    @staticmethod
    def _validate(v: Any) -> Any:
        if isinstance(v, BlockList):
            return v
        elif isinstance(v, list):
            for item in v:
                if not isinstance(item, BlockChunk):
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
        
    def __repr__(self) -> str:
        return f"BlockSent({super().__repr__()})"



class BlockList(UserList[BaseBlock], BaseBlock):
    __slots__ = [
        "default_sep",
    ]
    
    def __init__(
        self, 
        blocks: Sequence[BaseBlock] | None = None, 
        index: int | None = None,
        parent: "BaseBlock | None" = None,
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: "dict[str, FieldAttrBlock] | None" = None,
        id: str | None = None,
        styles: list[str] | None = None,
        sep: str = " ",
    ):
        if blocks is None:
            blocks = []

        UserList.__init__(self, blocks)
        BaseBlock.__init__(self, parent=parent, index=index)
        for block in blocks:
            block.parent = self.parent
        self.default_sep = sep
            
            
    @property
    def path(self) -> list[int]:
        if self.parent is None:
            raise ValueError("BlockList has no parent")
        return self.parent.path
    
    @property
    def logprob(self) -> float | None:
        return sum(block.logprob for block in self if block.logprob is not None)
    
    
    @property
    def last(self) -> BlockChunk:
        if not self:
            UserList.append(self, BlockSent(sep=self.default_sep, parent=self))
        return self[-1]
    
    
    def model_dump(self):
        dump = super().model_dump()
        dump["_type"] = "BlockList"
        dump["blocks"] = [b.model_dump() for b in self]
        return dump
    
    def append(self, content: "BlockChunk | BlockSent | Block"):
        if isinstance(content, BlockSent):            
            UserList.append(self, content)
        elif isinstance(content, Block):
            UserList.append(self, content)
        elif isinstance(content, BlockChunk):
            if self._should_add_sentence():
                UserList.append(self, BlockSent(sep=self.default_sep, parent=self))            
            self.last.append(content)
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
            
            # content = BlockSent([content])
            # UserList.append(self, content)
        content.parent = self          
        content.index = len(self)
        return self
    
    def _should_add_sentence(self):
        if not len(self):
            return True
        if not isinstance(self.last, BlockSent):
            return True
        if self.last.has_eol:
            return True
        return False
    
    @classmethod
    def model_validate(cls, data: dict):
        if "_type" not in data or data["_type"] != "BlockList":
            raise ValueError(f"Invalid or missing _type for BlockList: {data.get('_type')}")
        data = dict(data)
        data.pop("_type")
        blocks_data = data.pop("blocks", [])
        blocks = [BlockChunk.model_validate(b) for b in blocks_data]
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
            elif isinstance(block, Block):
                return block.get(tag)
        return None
        
        
    
        
    @staticmethod
    def _validate(v: Any) -> Any:
        if isinstance(v, BlockList):
            return v
        elif isinstance(v, list):
            for item in v:
                if not isinstance(item, BlockChunk):
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
        
    def __repr__(self) -> str:
        return f"BlockList({super().__repr__()})"



def parse_content(content: ContentType | BaseBlock | list[str] | None = None, **kwargs: Unpack[BlockParams]) -> BlockChunk:
    if content is None:
        return BlockChunk(**kwargs)
    elif isinstance(content, BlockChunk):
        return content
    elif isinstance(content, list):
        return BlockChunk(content, **kwargs)
    elif isinstance(content, str):
        return BlockChunk(content, **kwargs)
    else:
        raise ValueError(f"Invalid content type: {type(content)}")
      
      
        
class Block(BaseBlock):
    
    __slots__ = [
        "root",
        "children",
        "role",        
        "tags",
        "styles",      
        "attrs",
    ]
    
    # def __init__(
    #     self, 
    #     root: BlockChunk | BlockList | None = None, 
    #     children: BlockList | None = None,         
    #     **kwargs: Unpack[BlockParams]
    # ):
    def __init__(
        self, 
        root: ContentType | BlockChunk | BlockList | None = None, 
        children: BlockList | None = None,                 
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: "dict[str, FieldAttrBlock] | None" = None,
        id: str | None = None,
        styles: list[str] | None = None,
        index: int | None = None,
        parent: "BaseBlock | None" = None,
    ):
        super().__init__(parent=parent, index=index, id=id)
        self.role: str | None = role
        self.tags: list[str] = tags or []
        self.styles: list[str] | None = styles or parse_style(style)
        self.attrs: dict[str, FieldAttrBlock] = get_attrs(attrs)        
        self.root = BlockSent(index=self.index, parent=self)
        self.children = BlockList(children or [], index=self.index, parent=self)
        
        root_block = self._process_content(root) if root is not None else None
        if root_block is not None:
            self.root.append(root_block)
        

        # if isinstance(root_block, BlockChunk):
        #     self.root: BlockList = BlockList([root_block], parent=self)
        # elif isinstance(root_block, BlockList):
        #     self.root: BlockList = root_block
        # else:
        #     self.root: BlockList = BlockList([], parent=self)
        # if children is None:
        #     self.children: BlockList = BlockList([], parent=self)
        # else:
        #     self.children: BlockList = children
    @property
    def path(self) -> list[int]:
        if self.parent is None:
            return [self.index]
        return self.parent.path + [self.index]

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
       
    def field(self, name: str, type: Type, attrs: dict[str, str] | None = None) -> "FieldBlock":
        # block = FieldBlock(name, type, attrs=attrs)
        ctx = FieldBlock(
            name,
            type=type,
            attrs=attrs,
            role=self.role,
            parent=self.parent,            
            styles=["xml"],
        )
        self.append_child(ctx)
        return ctx
    
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
    
    def __call__(
        self, 
        content: ContentType | BaseBlock | list[str] | None = None, 
        role: str | None = None,
        tags: list[str] | None = None,
        style: str | None = None,
        attrs: "dict[str, FieldAttrBlock] | None" = None,
    ) -> "Block":        
        ctx = Block(
            content,
            index=len(self.children) + 1,
            role=role,
            tags=tags,            
            parent=self,            
            style=style,
            attrs=attrs,
        )
        self.children.append(ctx)        
        return ctx
    
    
    def __add__(self, other: ContentType | BlockChunk | tuple[ContentType, ...]):
        if isinstance(other, Block):
            for rc in other.root:
                self.append_root(rc)
        else:
            block = self._process_content(other)
            self.append_root(block)
        return self
    
    
    def __truediv__(self, other: "ContentType | BlockChunk | Block"):
        if isinstance(other, Block):
            self.append_child(other)
        else:
            block = self._process_content(other)
            self.append_child(block)
        return self
    
    
    
    def __iadd__(self, other: ContentType | BlockChunk):
        # if isinstance(other, ContentType):            
        #     other = Block(other)        
        #     self.append_root(other)
        # elif isinstance(other, Block):
        #     self.append_child(other, as_line=True)
        # elif isinstance(other, tuple):
        #     for c in other:
        #         if isinstance(c, ContentType):
        #             c = Block(c)
        #         self.append_root(c)
        # else:
        #     raise ValueError(f"Invalid content type: {type(other)}")
        block = self._process_content(other)
        self.append_child(block)
        return self
    
    
    def __itruediv__(self, other: ContentType | BlockChunk):
        # if not isinstance(other, Block):
        #     if isinstance(other, tuple):
        #         other = BlockList([Block(item) for item in other], style="list:row")                
        #     else:
        #         other = Block(other)
        block = self._process_content(other)
        self.append_child(block)
        return self
    

    
    def append_child(self, content: ContentType | BlockChunk):
        block = self._process_content(content)
        self.children.append(block)
        return self
        
    
    def append_root(self, content: ContentType | BlockChunk):
        block = self._process_content(content)
        self.root.append(block)
        return self
    
    
    def _process_content(self, content: ContentType | BlockChunk):
        if isinstance(content, BlockChunk):
            return content
        elif isinstance(content, str):
            return BlockChunk(content, parent=self)
        elif isinstance(content, int):
            return BlockChunk(str(content), parent=self)
        elif isinstance(content, float):
            return BlockChunk(str(content), parent=self)
        elif isinstance(content, bool):
            return BlockChunk(str(content), parent=self)
        elif isinstance(content, list):
            return BlockList(content, parent=self)
        elif isinstance(content, BaseBlock):
            return content        
        else:
            path = self.path
            raise ValueError(f"Invalid content type: {type(content)} for path: {path}")
    
    
    def response_schema(self, name: str | None = None):
        name = name or "response_schema"
        block = Block(tags=[name])
        self.append_child(block)
        return block
    
    
    def traverse(self):
        yield self.root
        for child in self.children:
            if isinstance(child, Block):
                yield from child.traverse()
            else:
                yield child
    
    
    def get(self, tag: str):
        tag = tag.lower()
        for child in self.children:
            if isinstance(child,Block):
                if tag in child.tags:
                    return child            
                block = child.get(tag)
                if block:
                    return block
        return None

    def get_field(self):
        for child in self.children:
            if isinstance(child, FieldBlock):
                return child
            elif isinstance(child, Block):
                for b in child.root:
                    if isinstance(b, FieldBlock):
                        return b
        return None
    
    def model_dump(self):
        dump = super().model_dump()
        # dump = self.base_model_dump()
        dump["_type"] = "Block"
        dump["root"] = self.root.model_dump()
        dump["children"] = [c.model_dump() for c in self.children]
        dump["styles"] = self.styles
        dump["tags"] = self.tags
        dump["attrs"] = self.attrs
        dump["role"] = self.role
        dump["id"] = self.id
        
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
        if isinstance(v, Block):
            return v
        elif isinstance(v, list):
            for item in v:
                if not isinstance(item, BlockChunk):
                    raise ValueError(f"Invalid block list: {v}")
            return BlockList(v)
        else:
            raise ValueError(f"Invalid block list: {v}")

    @staticmethod
    def _serialize(v: Any) -> Any:
        if isinstance(v, Block):
            return v.model_dump()
        else:
            raise ValueError(f"Invalid block list: {v}")
    
    def build_response(self):
        def _clone_target_node(n: Block) -> ResponseBlock:
            return ResponseBlock(                
                schema=n, 
                tags=n.tags,                           
            )
        
        def _is_target(node: BaseBlock) -> bool:
            return isinstance(node, FieldBlock)
        return self.reduce_tree(_is_target, _clone_target_node)
        
        
    def reduce_tree(self, is_target: Callable[[BaseBlock], bool] | None = None, clone_target_node = None) -> "ResponseBlock":
        """Return a forest containing only target-type nodes, attached under their
        nearest target-type ancestor from the original tree."""
        dummy_children: List[BaseBlock] = []
        stack: List[Block] = []  # stack of cloned target nodes
        
        # def _clone_target_node(n: Block) -> ResponseContext:
        #     # Copy only what you need; children will be filled during reduction.
        #     for b in n.root:
        #         if isinstance(b, FieldBlock):
        #             f = copy.deepcopy(b)
        #             f.attrs = copy.deepcopy(n.attrs)
        #             return ResponseContext(f)
        #     raise ValueError("No field block found")
        
        # def _is_target(node: BaseBlock) -> bool:
        #     if isinstance(node, FieldBlock):
        #         return True
        #     elif isinstance(node, Block):
        #         for b in node.root:
        #             if isinstance(b, FieldBlock):
        #                 return True
        #     return False
        

        
        # is_target = is_target or _is_target
        # clone_target_node = clone_target_node or _clone_target_node

        def dfs(u: Block):
            created = None
            if is_target(u):
                created = clone_target_node(u)
                if stack:
                    stack[-1].children.append(created)
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
        res = Block(children=BlockList(dummy_children))
        return res
        
    def __repr__(self) -> str:
        root = self.root.render() if self.root else ''
        tags = ','.join(self.tags) if self.tags else ''
        tags = f"[{tags}] " if tags else ''
        return f"Block({tags}root={root}, children={self.children})"


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


class FieldBlock(Block):
    
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
        super().__init__(name, tags=tags, style=style, id=id, index=index, parent=parent, attrs=attrs, styles=styles)
        if not type:
            raise ValueError("type is required")
        self.type = type
        self.name = name
        
        



class FieldContext(Block):
    pass



class ResponseBlock(Block):
    
    def __init__(
        self, 
        schema: FieldBlock, 
        children: BlockList | None = None, 
        tags: list[str] | None = None, 
        style: str | None = None,
        id: str | None = None,
        index: int | None = None,
        parent: "BaseBlock | None" = None,
    ):
        if schema.name not in tags:
            tags = [schema.name] + (tags or [])
        super().__init__(children=children, tags=tags, style=style, id=id, index=index, parent=parent)
        self.root.default_sep = ""
        self.children.default_sep = ""
        self.schema = schema
        self._value = None
        self.postfix: BlockList | None = None
    
    @property
    def name(self) -> str:
        return self.schema.name
    
    def _cast(self, content: str):
        if self.schema.type == str:
            return content
        elif self.schema.type == int:
            return int(content)
        elif self.schema.type == float:
            return float(content)
        elif self.schema.type == bool:
            return bool(content)
        elif self.schema.type == list:
            return content.split(",")
        elif self.schema.type == dict:
            return json.loads(content)
        
    def __getitem__(self, key: str):
        return self.attrs[key]
    
    def __setitem__(self, key: str, value: Any):
        self.attrs[key] = value
    
    def set_attributes(self, attrs: dict[str, str]):
        for k, v in attrs.items():
            if k in self.schema.attrs:
                value = self.schema.attrs[k].parse(v)
                self.attrs[k] = value
            else:
                raise ValueError(f"Attribute {k} not found in schema")
    
    
    def commit(self):
        content = self.children.render()
        content = content.strip()
        content = textwrap.dedent(content)
        self._value = self._cast(content)
        return self
    
    @property
    def value(self):
        return self._value
    
    
    def __repr__(self) -> str:
        root = self.root.render() if self.root else ''
        tags = ','.join(self.tags) if self.tags else ''
        tags = f"[{tags}] " if tags else ''
        return f"ResponseContext({tags}root={root}, children={self.children})"
    
    
    


        
        
    

class BlockSchema(Block):
      
    def __init__(self, name: str = "schema"):
        super().__init__(tags=[name])


    
    



class Blockable(Protocol):
    def block(self) -> BlockChunk:
        ...









def block(
    *content: ContentType | BlockChunk | list,
    role: str | None = None,
    tags: list[str] | None = None,
    style: str | None = None,
    attrs: dict | None = None,
):
    return BlockChunk(
        *content,
        role=role,
        tags=tags,
        style=style,
        attrs=attrs,
    )