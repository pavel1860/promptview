from typing import Any, Dict, List, Literal, Optional, Type, Union
from pydantic import BaseModel

from promptview.block.block import Block


ToolChoice = Literal['auto', 'required', 'none']





class ErrorMessage(Exception):
    
    def __init__(self, error_content: str, should_retry: bool = True) -> None:
        self.error_content = error_content
        self.should_retry = should_retry
        super().__init__(f"Output parsing error: {error_content}")
        
    def to_block(self, output_model: Type[BaseModel] | None = None, role: str = "user", tags: List[str] = ["error"]) -> Block:
        with Block(tags=tags, role=role) as b:
            b.append(self.error_content)
            if output_model:
                b /= "do not add any other text or apologies"
                b /= "use the output format as provided to generate your answer"                
        return b
    