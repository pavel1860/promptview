from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel

from promptview.prompt.block6 import Block


ToolChoice = Literal['auto', 'required', 'none']





class ErrorMessage(Exception):
    
    def __init__(self, error_content: str, should_retry: bool = True) -> None:
        self.error_content = error_content
        self.should_retry = should_retry
        super().__init__(f"Output parsing error: {error_content}")
        
    def to_block(self) -> Block:
        with Block(tags=["error"], role="user") as b:
            b.append(self.error_content)
        return b