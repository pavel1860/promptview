from typing import Any, Generic, Text, Type, TypeVar
from typing import get_type_hints, List
from typing import get_args, get_origin, List
from uuid import uuid4
import uuid
from .block import Block, BlockSequence, BlockSent, BlockChunk, BlockSchema


BaseContent = str | int | float | bool | None

CONTENT = TypeVar("CONTENT")





class StyleMeta(type):
    _registry: dict[str, "StyleMeta"] = {}
    _styles: dict[str, "BlockStyle"] = {}
    
    def __new__(cls, name, bases, attrs):        
        new_cls = super().__new__(cls, name, bases, attrs)
        cls._registry[name] = new_cls
        if styles := attrs.get("styles"):
            for style in styles:
                cls._styles[style] = new_cls()
        return new_cls
    
    @classmethod
    def resolve(cls, name: str) -> "BlockStyle":
        return cls._styles[name]
    

# def resolve_style(target: Block) -> "Block":
#     if target.styles:
#         lookup = {}
#         for style in target.styles:
#             if style in StyleMeta._styles:
#                 block_style = StyleMeta.resolve(style)
#                 lookup[block_style.target] = block_style
#         # target = target.copy(overrides={"styles":[]})
#         if styler:=lookup.get("text", TextStyle()):
#             target.content = styler(target.content)
#         if styler:=lookup.get("block", BlockStyle()):
#             target = styler(target)
#                 # return block_style(target.copy(overrides={"styles":[]}))
#     return target


def resolve_style(target: Block, effects: str) -> dict:
    lookup = {}
    if target.styles:        
        for style in target.styles:
            if style in StyleMeta._styles:
                block_style = StyleMeta.resolve(style)
                if block_style.effects == effects:
                    lookup[block_style.target] = block_style        
    return lookup



def apply_style(target):
    lookup = resolve_style(target, "content")
    if styler:=lookup.get("text", TextStyle()):
        target.content = styler(target.content)
    if target.parent:
        parent_lookup = resolve_style(target.parent, "children")
        if styler:=parent_lookup.get("text"):
            target.content = styler(target.content)
    if styler:=lookup.get("block", BlockStyle()):
        target = styler(target)
    
    return target


def render_text(target) -> str:
    prefix = ""
    content = ""
    children_content = ""
    postfix = ""
    if target.prefix is not None:
        prefix = render(target.prefix)
    if target.content is not None:
        content = render(target.content)
    if target.postfix is not None:
        postfix = render(target.postfix)
    if target.children:
        children_content = "".join(render(c) for c in target.children)
    return f"{prefix}{content}{children_content}{postfix}"


def render(target) -> str:    
    if type(target) is str:
        return target
    elif type(target) in (int, float, bool):
        return str(target)
    elif type(target) is list:
        return "".join(render(c) for c in target)
    # elif type(target) is Block:
    elif isinstance(target, Block):
        target = apply_style(target)
        prefix = ""
        content = ""
        postfix = ""
        children_content = ""
        if target.prefix is not None:
            prefix = render_text(target.prefix)
        if target.content is not None:
            content = render_text(target.content)
        if target.postfix is not None:
            postfix = render_text(target.postfix)
        if target.children:
            children_content = "".join(render(c) for c in target.children)
        return f"{prefix}{content}{children_content}{postfix}"
    # elif type(target) is BlockSent:
    #     if target.content is not None:
    #         return render(target.content)
    #     elif target.children:
    #         return "".join(render(c) for c in target.children)
    #     else:
    #         return ""
    elif type(target) is BlockChunk:
        if target.content is not None:
            return render(target.content)
        else:
            return ""
    else:
        raise ValueError(f"Unknown type: {type(target)}") 
    

class BlockStyle(metaclass=StyleMeta):
    styles = []
    target = "block"
    effects = "all"
    
    def __call__(self, block: Block):
        for child in block.children:
            child.prefix.insert("\n", 0)
        return block
    
    
class TextStyle(metaclass=StyleMeta):
    styles = []
    target = "text"
    effects = "all"
    
    def __call__(self, text: BlockSent):
        return text
    
    
class Markdown(TextStyle):
    styles = ["md"]
    effects = "content"
    
    def __call__(self, text: BlockSent):
        text.prefix = "# "
        # text.postfix = "\n"
        return text
        # return Block(
        #     prefix=Block("#", postfix=" "),
        #     content=block,
        #     postfix="\n"            
        # )
    
    
class AstrixList(TextStyle):
    styles = ["ast-li"]
    effects = "children"
    
    def __call__(self, text: BlockSent):
        text.prefix ="* " + text.prefix
        # text.postfix = "\n"
        return text
        # return Block(
        #     prefix=Block(f"*", postfix="\n"),
        #     content=block,
        # )
    


class NumberedList(TextStyle):
    styles = ["numbered-list", "num-li"]
    effects = "children"
    
    def __call__(self, text: BlockSent):
        text.prefix += f"{text.index + 1}. "
        return text
    
    
    
class XMLStyle(BlockStyle):
    styles = ["xml"]
    effects = "content"
    
    def __call__(self, block: Block):        
        if not block.children:
            block.content.prefix = f"<"
            block.content.postfix = f"/>"
        else:
            block = super().__call__(block)
            block.content.prefix = f"<"        
            block.content.postfix = f">"
            block.postfix = block.content.copy()
            block.postfix.prefix = f"\n</"
            block.postfix.postfix = f">"
        return block
    