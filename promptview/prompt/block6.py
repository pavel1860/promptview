
from typing import Any
from promptview.prompt.style import StyleDict






class BlockContent:
    
    def __init__(self, content: Any, tags: list[str] | None = None, style: StyleDict | None = None, depth: int = 0):
        self.content = content
        self.tags = tags or []
        self.style = style or {}
        self.depth = depth
        
        
        
    def get_style(self, property_name: str, default: Any = None) -> Any:
        return self.style.get(property_name, default)




        
        
        
        