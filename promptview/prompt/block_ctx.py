from typing import Any, Type
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import StyleDict





class ContextStack:
    _ctx_stack: list[BaseBlock]
    
    def __init__(self):
        self._ctx_stack = []
        
    def __getitem__(self, idx: int) -> BaseBlock:
        return self._ctx_stack[idx]
    
    def __len__(self) -> int:
        return len(self._ctx_stack)
    
    def root(self) -> BaseBlock:
        if not self._ctx_stack:
            raise ValueError("No context stack")
        return self._ctx_stack[0]
    
    def push(self, block: BaseBlock):
        self._ctx_stack.append(block)
        
    def pop(self):
        return self._ctx_stack.pop()
    
    def top(self):
        return self._ctx_stack[-1]



class Block(object):
    
    _block_type_registry: dict[Type, Type[BaseBlock]]
    _ctx: ContextStack
    
    
    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, "_block_type_registry"):
            cls._block_type_registry = {}
        return super().__new__(cls)

        
    def __init__(
        self,
        value: Any | None = None,
        tags: list[str] | None = None,
        style: StyleDict | None = None,
        # ctx_stack: "List[Block] | None" = None, 
    ):
        self._ctx = ContextStack()
        inst = self._build_instance(value, tags, style)
        self._main_inst = inst
    
    @property
    def root(self):
        return self._ctx[0]
    
    def __call__(self, value: Any, tags: list[str] | None = None, style: StyleDict | None = None, **kwargs):       
        self._append(value, tags, style)
        return self
    
    def _append(self, value: Any, tags: list[str] | None = None, style: StyleDict | None = None):
        inst = self._build_instance(value, tags, style)        
        self._ctx[-1].append(inst)
        return inst

    
    @property
    def last(self):
        """
        The last block in the context stack
        """
        if not self._ctx:
            raise ValueError("No context stack")
        if not self._ctx[-1].items:
            return self._ctx[-1]
        return self._ctx[-1].items[-1]
        
    def __enter__(self):        
        if not self._ctx:
            self._ctx.push(self._main_inst)
        else:
            self._ctx.push(self.last)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if len(self._ctx) > 1:
            self._ctx.pop()

    
    @classmethod
    def register(cls, typ: Type, block_type: Type[BaseBlock]):
        if not hasattr(cls, "_block_type_registry"):
            cls._block_type_registry = {}
        cls._block_type_registry[typ] = block_type    
    
        
    def _build_instance(self, content: Any, tags: list[str] | None = None, style: StyleDict | None = None, parent: "BaseBlock | None" = None):
        # if "depth" not in kwargs:
            # kwargs["depth"] = depth
        inst = self.__class__._block_type_registry[type(content)](
                content=content, 
                tags=tags, 
                style=style, 
                parent=parent,
                depth=len(self._ctx) + 1
            )
        return inst
        
    def __add__(self, content: Any):
        inst = self._append(content)
        return inst
    
    def __iadd__(self, content: Any):
        self._append(content)
        return self
    
    # def render(self):
    #     return self._ctx[-1].render()
    
    
    
    
    
    


def print_block(b, depth=0):
    tags = f"{b.tags}" if b.tags else ""
    print(str(depth) + " " + tags + "  " * depth + str(b.content))
    for item in b.items:
        print_block(item, depth+1)
        
        
        
        
        
        
        
        
