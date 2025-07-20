import textwrap
from typing import TYPE_CHECKING

if TYPE_CHECKING:   
    from promptview.block.block7 import Block

def indent(texts: list[str], indent: str = " "):
    return [textwrap.indent(text, indent) for text in texts]


def render(block: "Block", indent: str | None = None) -> str:
    content = " ".join(str(chunk) for chunk in block.content)
    children_content = [render(child, " ") for child in block.children]       
    content = "\n".join([content] + children_content)
    if indent is not None:
        content = textwrap.indent(content, indent)    
    return content
