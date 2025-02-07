import contextvars
import textwrap
from typing import List, Literal, Type
import uuid

from pydantic import BaseModel

from promptview.utils.model_utils import schema_to_ts


TitleType = Literal["md", "xml"]

block_ctx = contextvars.ContextVar("block_ctx")


def sanitize_value(value: str):
    return textwrap.dedent(value).strip()


def instantiate_block(instance: "StrBlock"):
    instance._items = []
    instance._token = None
    instance._id = str(uuid.uuid4())
    return instance

def connect_block(instance: "StrBlock"):
    try:
        instance._parent = block_ctx.get()
        if instance._parent is not None:            
            instance._parent.append(instance)
            instance._depth = instance._parent._depth + 1
    except LookupError:
        pass
    return instance

class StrBlock(str):
    
    _items: list["StrBlock | TitleBlock | ListBlock"] = []
    _token: contextvars.Token | None = None
    _parent: "StrBlock | None" = None
    _id: str | None = None
    _style: dict | None = None
    _depth: int = 1
    
    
    # def __new__(cls, value, _auto_append: bool = True):
    #     # Remove leading and trailing whitespace and dedent the value
    #     value = textwrap.dedent(value).strip() 
    #     # Create the instance using str's __new__        
    #     instance = super().__new__(cls, value)
    #     # Attach extra attributes to the instance
    #     instance._items = []
    #     instance._token = None
    #     instance._id = str(uuid.uuid4())
    #     if _auto_append:
    #         try:
    #             instance._parent = block_ctx.get()
    #             if instance._parent is not None:            
    #                 instance._parent.append(instance)
    #                 instance._depth = instance._parent._depth + 1
    #         except LookupError:
    #             pass
    #     return instance
    def __new__(cls, value, _auto_append: bool = True):
        value = sanitize_value(value)
        instance = super().__new__(cls, value)
        instance = instantiate_block(instance)
        if _auto_append:
            instance = connect_block(instance)
        return instance
    

    def append(self, item: "StrBlock | str"):
        if isinstance(item, str):
            self._items.append(StrBlock(item, _auto_append=False))
        else:
            self._items.append(item)
     
    def render_items(self):
        content = "\n".join([item.render() for item in self._items])      
        content = textwrap.indent(content, "   ")
        return content
        
    def render(self):
        content = self
        if self._items:
            content = content + "\n" + self.render_items()
        return content
        
    def show(self):
        # self is the string content
        print("Content:", self)
        print("Extra info:", self.ttype)
        
    def __enter__(self):
        self._token = block_ctx.set(self)
        return self
    
    def __exit__(self, exc_type, exc_value, traceback):
        if self._token is not None:
            block_ctx.reset(self._token)
        return False
    
    
class TitleBlock(StrBlock):
    _type: TitleType
    
    # def __new__(cls, value, type: TitleType, _auto_append: bool = True):
    #     instance = super().__new__(cls, value, _auto_append)
    #     instance._type = type
    #     return instance
    def __new__(cls, value, type: TitleType, _auto_append: bool = True):
        instance = super().__new__(cls, value, False)
        instance._type = type
        if _auto_append:
            instance = connect_block(instance)
        return instance
      
    
    def render(self):
        content = self.render_items()
        if self._type == "md":
            content = "#" * self._depth + " " + self + "\n" + content
            
        elif self._type == "xml":
            content = "<" + self + ">\n" + content + "\n</" + self + ">\n"
        return content
    
class ListBlock(TitleBlock):
    
    def __new__(cls, value, type: TitleType, _auto_append: bool = True):
        instance = super().__new__(cls, value, type, _auto_append)
        instance._type = "list"
        return instance
    
    
    
    
    
    
    
    
    
    
    
    
# class Block:
    
    
#     @staticmethod
#     def title(value: str, type: TitleType):
#         return TitleBlock(value, type)
    
#     @staticmethod
#     def list(value: str, type: TitleType):
#         return ListBlock(value, type)
    
    
#     @staticmethod
#     def model_dump(model: Type[BaseModel], format: str = "ts"):    
#         if format == "ts":
#             content = schema_to_ts(model)
#         else:
#             content = model.model_json_schema()        
#         return StrBlock(content)
    
#     @staticmethod
#     def li(item: str):
#         return StrBlock(item, _auto_append=False)

class Block:
            
    def title(self, value: str, type: TitleType):
        return TitleBlock(value, type)
    
    def list(self, value: str, type: TitleType):
        return ListBlock(value, type)
    
    
    def model_dump(self, model: Type[BaseModel], format: str = "ts"):    
        if format == "ts":
            content = schema_to_ts(model)
        else:
            content = model.model_json_schema()        
        return StrBlock(content)
    
    def li(self, item: str):
        return StrBlock(item, _auto_append=False)
    
    
    def __call__(self, target: StrBlock | List[str] | str):
        _target = None
        if isinstance(target, StrBlock):
            _target = target
        elif isinstance(target, str):
            _target = StrBlock(target, _auto_append=True)
        elif isinstance(target, list):
            _target = [StrBlock(item, _auto_append=True) for item in target]
        else:
            raise ValueError(f"Invalid target type: {type(target)}")

        return _target
    
block = Block()