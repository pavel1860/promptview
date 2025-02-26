from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel


ToolChoice = Literal['auto', 'required', 'none']





class ErrorMessage(Exception):
    
    def __init__(self, error_content: str, should_retry: bool = True) -> None:
        self.error_content = error_content
        self.should_retry = should_retry
        super().__init__(f"Output parsing error: {error_content}")
        
    def to_message(self) -> dict:
        return {
            "role": "user",
            "content": self.error_content
        }