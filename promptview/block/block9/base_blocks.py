from typing import Any, Generic, TypeVar
from uuid import uuid4




BaseContent = str | int | float | bool | None

class UnsetType:
    __slots__ = ()

    def __repr__(self):
        return "<UNSET>"

CONTENT = TypeVar("CONTENT")


class BaseBlock(Generic[CONTENT]):
    __slots__ = [
        "content",
        "parent",
        "prefix",
        "postfix", 
        "id",      
    ]    
    
    def __init__(
        self,
        content: CONTENT | None = None,
        *,
        parent: "BlockSequence | None" = None,
        id: str | None = None,
        prefix: CONTENT | None = None,
        postfix: CONTENT | None = None,
    ):
        self.content: CONTENT | None = content
        self.parent: "BlockSequence | None" = parent
        self.prefix: CONTENT | None = prefix
        self.postfix: CONTENT | None = postfix
        self.id: str = id or uuid4().hex[:8]
    
    @property
    def path(self) -> list[int]:
        if self.parent is None:
            return []
        if self.index is None:
            raise ValueError("Block has no index")
        return self.parent.path + [self.index]
    
    @property
    def index(self) -> int | None:
        if self.parent is None:
            return None
        return self.parent.index_of(self)
    
    
    def model_dump(self):
        return {
            "_type": self.__class__.__name__,
            "id": self.id,
            "content": self.content,
            "prefix": self.prefix,
            "postfix": self.postfix,
            "index": self.index,
            "path": [p for p in self.path],
            "parent_id": self.parent.id if self.parent else None,
        }
        
    def repr_tree(self, verbose: bool = False):
        return f"{self.path}  BaseBlock({self.content})"
    
    def print_tree(self, verbose: bool = False):
        print(self.repr_tree(verbose=verbose))
    


CHILD = TypeVar("CHILD", bound=BaseBlock)

PathType = list[int] | int


class BlockSequence(BaseBlock, Generic[CHILD]):
    
    __slots__ = [
        "children",
        "_id2index",
        "default_sep",        
    ]
    
    def __init__(
        self,
        children: list[CHILD] | None = None,
        parent: "BlockSequence | None" = None,
        default_sep: str = " ",
        id: str | None = None,
        prefix: BaseContent | None = None,
        postfix: BaseContent | None = None,
    ):
        BaseBlock.__init__(self, parent=parent, prefix=prefix, postfix=postfix, id=id)
        self.children: list[CHILD] = []
        self._id2index: dict[str, int] = {}
        self.parent: "BlockSequence | None" = parent
        self.id: str = uuid4().hex[:8]
        self.default_sep = default_sep
        if children is not None:
            for child in children:
                self.append(child)
                
    def promote_content(self, content: Any, prefix: BaseContent | None = None, postfix: BaseContent | None = None) -> CHILD:
        raise NotImplementedError("promote_content is not implemented")
        
    @property
    def path(self) -> list[int]:
        if self.parent is None:
            return []
        if self.index is None:
            return self.parent.path
        return self.parent.path + [self.index]
    
    @property
    def index(self) -> int | None:
        if self.parent is None:
            return None
        return self.parent.index_of(self)
        
    def index_of(self, child: CHILD) -> int | None:
        return self._id2index.get(child.id)
    
    def _parse_path(self, path: PathType):
        if isinstance(path, int):
            return [path]
        return [p for p in path]
    
    
    # def path_traverse(self, path: list[int] | int):
    
    def path_get(self, path: PathType) -> "BlockSequence | BaseBlock | None":
        _path = self._parse_path(path)
        target = self
        while _path:
            idx = _path.pop(0)
            if not isinstance(target, BlockSequence):
                if len(_path) == 0:
                    return target
                raise ValueError(f"Invalid path: {path}, target is not a BlockSequence and not supporting insert")
            if idx >= len(target.children):
                return None            
            target = target.children[idx]
        return target
    
    
    def path_exists(self, path: PathType) -> bool:
        path = self._parse_path(path)
        target = self
        while path:
            idx = path.pop(0)
            if not isinstance(target, BlockSequence):
                return False
            if idx >= len(target.children):
                return False
            target = target.children[idx]
        return True
    
    def _get_sep(self, sep: str | None = None) -> str | None:
        if len(self.children) == 0:
            return None
        if sep is None:
            return self.default_sep
        return sep
    
    @property
    def last_child(self) -> CHILD | None:
        if len(self.children) == 0:
            return None
        return self.children[-1]
    
    
    def append_child(self, child: CHILD):
        self.children.append(child)
        child.parent = self
        if child.id in self._id2index:
            raise ValueError(f"Child with id {child.id} already exists")
        self._id2index[child.id] = len(self.children) - 1
        return child
    
    def insert_child(self, index: int, child: CHILD):
        self.children.insert(index, child)
        child.parent = self
        if child.id in self._id2index:
            raise ValueError(f"Child with id {child.id} already exists")
        self._id2index[child.id] = index
        return child
    
    
    def replace_child(self, index: int, child: CHILD):
        child.parent = self
        del self._id2index[self.children[index].id]
        self.children[index] = child
        if child.id in self._id2index:
            raise ValueError(f"Child with id {child.id} already exists")
        del self._id2index[self.children[index].id]
        self._id2index[child.id] = index
        return child
    
    def append(
        self, 
        child: CHILD | BaseContent, 
        path: PathType | None = None, 
        sep: str | None = None,  
        prefix: BaseContent | None = None, 
        postfix: BaseContent | None = None
    ):
        sep = self._get_sep(sep)
        child = self.promote_content(child, prefix=sep, postfix=postfix)
        if not path:
            self.append_child(child)
            return child        
        path = self._parse_path(path)
        target = self.path_get(path)
        if target is None:
            raise ValueError(f"Invalid path: {path}, target not found")
        if not isinstance(target, BlockSequence):
            raise ValueError(f"Invalid path: {path}, target is not a BlockSequence and not supporting append")
        target.append_child(child)
        return child
    
    def extend(
        self, 
        children: list[CHILD],
        path: PathType | None = None,
        sep: str | None = None,
        prefix: BaseContent | None = None,
        postfix: BaseContent | None = None,
    ):
        for child in children:
            self.append(child, path=path, sep=sep, prefix=prefix, postfix=postfix)
        return self
    
    
    def insert(self, child: CHILD | BaseContent, path: PathType):
        child = self.promote_content(child)
        path = self._parse_path(path)
        if len(path) == 1:
            self.insert_child(path[0], child)
            return child
        idx = path.pop(-1)        
        target = self.path_get(path)
        if target is None:
            raise ValueError(f"Invalid path: {path}, target not found")
        if not isinstance(target, BlockSequence):
            raise ValueError(f"Invalid path: {path}, target is not a BlockSequence and not supporting insert")
        target.insert_child(idx, child)
        return child
    
    
    def replace(self, child: CHILD | BaseContent, path: PathType):
        child = self.promote_content(child)
        path = self._parse_path(path)
        if len(path) == 1:
            self.replace_child(path[0], child)
            return child
        idx = path.pop(-1)
        target = self.path_get(path)
        if target is None:
            raise ValueError(f"Invalid path: {path}, target not found")
        if not isinstance(target, BlockSequence):
            raise ValueError(f"Invalid path: {path}, target is not a BlockSequence and not supporting replace")
        target.replace_child(idx, child)
        return child
    
    
    
    def __iter__(self):
        return iter(self.children)
    
    def __len__(self):
        return len(self.children)
    
    def __getitem__(self, path: PathType):
        path = self._parse_path(path)
        target = self.path_get(path)
        if target is None:
            raise ValueError(f"Invalid path: {path}, target not found")
        return target
    
    def __eq__(self, other: object):
        if isinstance(other, BlockSequence):
            return self.children == other.children
        else:
            return False
        
        
        
    def model_dump(self):
        dump = {
            **super().model_dump(),
            "children": [child.model_dump() for child in self.children],
            "default_sep": self.default_sep,
        }
        
        return dump

    
    
    def repr_tree(self, verbose: bool = False):           
        res =  f"{self.path}  BlockSequence({self.id})"
        for child in self.children:
            res += f"\n{child.repr_tree()}"
        return res
    

        
        
        




