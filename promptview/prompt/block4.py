from collections import defaultdict
from abc import abstractmethod
from typing import Any, List, Type






class TagRegistry:
    
    tags: defaultdict[str, list["Block"]]
    
    def __init__(self):
        self.tags = defaultdict(list)

    def add(self, block: "Block"):
        for tag in block.tags:
            self.tags[tag].append(block)        
    
    def get(self, tag: str | list[str]) -> list["Block"]:
        if isinstance(tag, str):
            return self.tags[tag]
        else:
            return [block for t in tag for block in self.tags[t]]






# class MetaBlock(type):
    
#     def __new__(cls, name, bases, attrs):
#         attrs["__call__"] = BlockContext(cls)
#         return super().__new__(cls, name, bases, attrs)

     
        
        
class Block:
    
    tags: list[str]
    items: list["Block"]
    
    
    def __init__(self, tags: list[str] | None = None, depth: int = 1):
        self.tags = tags or []
        self.items = []
        self.depth = depth
        
        
    def append(self, item: "Block | Any"):
        # if not isinstance(item, Block):
            # item = self._build_instance(item)
        self.items.append(item)
        return item
        
    def __add__(self, other: "Block | Any"):
        item = self.append(other)
        return item
    
    def __iadd__(self, other: "Block | Any"):
        self.append(other)
        return self
       
    # def _build_instance(self, *args, **kwargs):
    #     print(self.__class__)     
    #     return self.__class__(*args, **kwargs)
    
    @classmethod
    def _build_instance(cls, *args, **kwargs): 
        return cls(*args, **kwargs)
    
    # def get_tags(self, tags: list[str] | None = None):
        # for 
        
        
    @abstractmethod
    def render(self):
        raise NotImplementedError("Subclasses must implement this method")
    
    
    @abstractmethod
    def parse(self, text: str):
        raise NotImplementedError("Subclasses must implement this method")
        
        
        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        pass
        
        







    
      
    
    
    
class BlockContext(object):
    
    _block_type_registry: dict[Type, Type[Block]]
    _ctx_stack: "List[Block]"
    
    
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_block_type_registry"):
            cls._block_type_registry = {}
        return super().__new__(cls)

        
    def __init__(
        self,
        value: Any | None = None,
        *args,
        **kwargs,
        # ctx_stack: "List[Block] | None" = None, 
    ):
        self._block = block
        # self._staged_inst = self._build_instance(value, *args, **kwargs)
        self._ctx_stack = []
        inst = self._build_instance(value, 1, *args, **kwargs)
        self._ctx_stack.append(inst)
        # self._ctx_stack.append(inst)
    
    
    def __call__(self, value: Any, *args, **kwargs):
        if self._staged_inst is not None:
            self._append(self._staged_inst)
        # self._staged_inst = self._build_instance(value, *args, **kwargs)
        inst = self._build_instance(value, depth=len(self._ctx_stack), *args, **kwargs)
        self._append(inst)
        return self
    
    @property
    def _staged_inst(self):
        curr_blk = self._ctx_stack[-1]
        if curr_blk.items:
            return curr_blk.items[-1]
        return curr_blk
        
    def __enter__(self):
        # if self._staged_inst is None:
        #     raise ValueError("No instance to append")
        self._ctx_stack.append(self._staged_inst)
        # self._staged_inst = None
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if len(self._ctx_stack) > 1:
            self._ctx_stack.pop()

        
    @classmethod
    def register(cls, typ: Type, block_type: Type[Block]):
        if not hasattr(cls, "_block_type_registry"):
            cls._block_type_registry = {}
        cls._block_type_registry[typ] = block_type    
    
        
    def _build_instance(self, value: Any, depth: int, *args, **kwargs):
        kwargs["depth"] = depth
        return self.__class__._block_type_registry[type(value)](value, *args, **kwargs)
    
    def _append(self, value: Any):
        self._ctx_stack[-1].append(value)
    
    def __add__(self, value: Any):
        inst = self._build_instance(value, depth=len(self._ctx_stack))
        self._append(inst)
        return inst
    
    def __iadd__(self, value: Any):
        inst = self._build_instance(value, depth=len(self._ctx_stack))
        self._append(inst)
        return self
    
    def render(self):
        return self._ctx_stack[-1].render()
    
    # def __getattr__(self, item):
        # return getattr(self.block, item)
    
    
    
    
    


