from dataclasses import dataclass






def compute_path(node: "Block") -> list[int]:
    path = []
    while node.parent is not None:
        path.append(node.index)
        node = node.parent
    return list(reversed(path))




class BlockMetadata:
    __slots__ = [
        "name",
        "role",
        "dtype",
        "tags",
        "styles",
        "attrs",
        "parent",
    ]
    
    
    def __init__(
        self,
        name: str | None = None,
        role: str | None = None,
        dtype: type | None = None,
        tags: list[str] | None = None,
        styles: list[str] | None = None,
        attrs: dict[str, str] | None = None,
    ):
        self.name = name
        self.role = role
        self.dtype = dtype
        self.tags = tags
        self.styles = styles
        self.attrs = attrs
        






ContentType = str


class Block:
    __slots__ = [
        "children",
        "parent",
        "index",
        "logprobs",
        "metadata",                
        "default_sep",
        "has_eol",
        "sep_list",
    ]
    
    children: list["ContentType | Block"]
    parent: "Block | None"
    index: int | None
    metadata: BlockMetadata | None
    logprobs: list[float] | None
    
    
    default_sep: str
    has_eol: bool
    sep_list: list[str]
    
    def __init__(
        self,
        content: "ContentType | Block",
        dtype: type | None = None,
        role: str | None = None,
        tags: list[str] | None = None,
        styles: list[str] | None = None,
        attrs: dict[str, str] | None = None,
        logprob: float | None = None,
        parent: "Block | None" = None,
        index: int | None = None,
        default_sep: str = " ",
        has_eol: bool = False,
        sep_list: list[str] | None = None,  
    ):        
        self.children  = []        
        self.parent = parent
        self.metadata = None
        self.index = index if index is not None else 0
        self.logprobs = [logprob] if logprob is not None else None
        self.default_sep = default_sep
        self.has_eol = has_eol
        self.sep_list = sep_list if sep_list is not None else []
        
        self.append(content)
        
        if role is not None:
            self.role = role
        if tags is not None:
            self.tags = tags
        if styles is not None:
            self.styles = styles
        if attrs is not None:
            self.attrs = attrs
        if dtype is not None:
            self.dtype = dtype
        
        
        

    @property
    def name(self) -> str | None:
        if self.metadata is None:
            return None
        return self.metadata.name
    
    @name.setter
    def name(self, value: str):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.name = value
    
    @property
    def role(self) -> str | None:
        if self.metadata is None:
            return None
        return self.metadata.role
    
    @role.setter
    def role(self, value: str):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.role = value
        
    @property
    def tags(self) -> list[str] | None:
        if self.metadata is None:
            return None
        return self.metadata.tags
    
    @tags.setter
    def tags(self, value: list[str]):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.tags = value
    
    @property
    def styles(self) -> list[str] | None:
        if self.metadata is None:
            return None
        return self.metadata.styles
    
    @styles.setter
    def styles(self, value: list[str]):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.styles = value
    
    @property
    def attrs(self) -> dict[str, str] | None:
        if self.metadata is None:
            return None
        return self.metadata.attrs
    
    @attrs.setter
    def attrs(self, value: dict[str, str]):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.attrs = value
    
    @property
    def logprob(self) -> float | None:
        return sum(self.logprobs) if self.logprobs is not None else None
    
        
        
    @property
    def dtype(self) -> type | None:
        if self.metadata is None:
            return None
        return self.metadata.dtype
    
    @dtype.setter
    def dtype(self, value: type):
        if self.metadata is None:
            self.metadata = BlockMetadata()
        self.metadata.dtype = value
    
    @property
    def path(self) -> list[int]:
        return compute_path(self)
    


    def _process_init_content(self, content: "ContentType | Block") -> list["ContentType | Block"]:
        if isinstance(content, Block):
            return [content]
        elif isinstance(content, str):
            return [content]
        elif isinstance(content, list):            
            raise ValueError("list is not allowed as a content")
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
    def _process_content(self, content: "ContentType | Block") -> "ContentType | Block":
        if isinstance(content, Block):
            return content
        elif isinstance(content, str):
            return content
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        
        
    def _try_promote_content(self, content: "ContentType | Block", parent: "Block | None" = None, index: int | None = None) -> "Block":
        if isinstance(content, Block):
            return content
        elif isinstance(content, str):
            
            content = Block(content)
            if parent is not None:
                if index is None:
                    raise ValueError("index is required when parent is provided")
                parent.replace_child(index, content, sep=parent.sep_list[index])
            return content
        else:
            raise ValueError(f"Invalid content type: {type(content)}")
        

        
    def _connect(self, index: int, content: "Block") -> "Block":
        content.parent = self
        content.index = len(self.children) if index == -1 else index 
        return content
    
    def insert_child(self, index: int, content: "ContentType | Block", sep: str):        
        if isinstance(content, Block):
            self._connect(index, content)
        if index == -1:
            self.children.append(content)
            self.sep_list.append(sep)
        else:            
            self.shift_children(index)
            self.children.insert(index, content)
            self.sep_list.insert(index, sep)            
        return content
    
    def replace_child(self, index: int, content: "ContentType | Block", sep: str):
        if isinstance(content, Block):
            self._connect(index, content)
        self.children[index] = content
        self.sep_list[index] = sep
        return content
    
    
    def append(self, content: "ContentType | Block", sep: str | None = None):
        sep = sep or self.default_sep
        if sep == "\n":
            if self.has_eol:
                raise ValueError("Cannot append to a list that has an end of line")
            self.has_eol = True
            sep = ""
        content = self._process_content(content)
        self.insert_child(-1, content, sep=sep)
        return self
    
    
    def append_path(self, path: list[int], content: "ContentType | Block", sep: str | None = None):
        sep = sep or self.default_sep
        target, parent = self.get_path_with_parent(path)
        target = self._try_promote_content(target, parent=parent, index=path[-1])
        target.insert_child(-1, content, sep=sep)
        return self

    
    def get_path(self, idx_path: list[int]) -> "Block | ContentType | Block":
        target = self
        for i,idx in enumerate(idx_path):
            if not isinstance(target, Block):
                raise ValueError(f"Invalid path: {idx_path}, target on path {idx_path[:i+1]} is {type(target)} and not a Block")
            target = target.children[idx]
        return target
    
    def get_path_with_parent(self, idx_path: list[int]) -> "tuple[Block | ContentType | Block, Block | None]":
        target = self
        parent = None
        for i,idx in enumerate(idx_path):
            if not isinstance(target, Block):
                raise ValueError(f"Invalid path: {idx_path}, target on path {idx_path[:i+1]} is {type(target)} and not a Block")
            parent = target
            target = target.children[idx]
        return target, parent
    
    def insert(self, idx_path: int | list[int], content: "ContentType | Block", sep: str | None = None):
        sep = sep or self.default_sep
        if isinstance(idx_path, int):
            idx_path = [idx_path]
        target, parent = self.get_path_with_parent(idx_path[:-1])        
        target = self._try_promote_content(target, parent=parent, index=idx_path[-2] if len(idx_path) > 1 else None)        
        content = self._process_content(content)
        target.insert_child(idx_path[-1], content, sep=sep)
        return self
    
    def replace(self, idx_path: int | list[int], content: "ContentType | Block", sep: str | None = None):
        sep = sep or self.default_sep
        if isinstance(idx_path, int):
            idx_path = [idx_path]
        target = self.get_path(idx_path[:-1])
        if not isinstance(target, Block):
            raise ValueError(f"Invalid path: {idx_path}, target on path {idx_path[:-1]} is {type(target)} and not a Block")        
        content = self._process_content(content)        
        target.replace_child(idx_path[-1], content, sep=sep)
        return self
    
    def shift_children(self, idx: int, shift: int = 1):
        for i in range(idx, len(self.children)):
            if isinstance(self.children[i], Block):
                self.children[i].index += shift
        return self
    
    def __repr__(self):
        content = "".join([f"{c}{s}" for c,s in zip(self.children, self.sep_list)  if isinstance(c, str)])
        content = f"'{content}'" if content else "''"
        tags =" [" + ",".join(self.tags) + "]" if self.tags else ""
        role = f" role={self.role}" if self.role else ""
        name = f" name={self.name}" if self.name else ""
        dtype = f" dtype={self.dtype}" if self.dtype else ""
        attrs = f" attrs={self.attrs}" if self.attrs else ""
        logprob = f" logprob={self.logprob}" if self.logprob else ""
        parent = f" parent={self.parent}" if self.parent else ""
        index = f" idx={self.index}" if self.index is not None else ""
        return f"Block{name}({content}{tags}{role}{dtype}{attrs}{logprob}{parent}{index})"