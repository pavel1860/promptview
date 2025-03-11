
import json
from typing import Any, Literal
import uuid
from pydantic import BaseModel
from promptview.prompt.block4 import BaseBlock
from promptview.prompt.style import InlineStyle



BlockRole = Literal["assistant", "user", "system", "tool"]

class LlmUsage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ToolCall(BaseModel):
    id: str
    name: str
    tool: dict | BaseModel
    
    @property
    def type(self):
        return type(self.tool)
    
    def to_json(self):
        return self.tool.model_dump_json() if isinstance(self.tool, BaseModel) else json.dumps(self.tool)




class LLMBlock(BaseBlock):
    """
    A block that represents an LLM call.
    """
    id: str
    model: str    
    run_id: str | None = None
    name: str | None = None
    role: BlockRole
    tool_calls: list[ToolCall]
    usage: LlmUsage
    
    
    def __init__(
        self, 
        content: Any | None = None, 
        role: BlockRole = "user", 
        id: str | None = None, 
        name: str | None = None,
        model: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        run_id: str | None = None,
        tags: list[str] | None = None, 
        style: InlineStyle | None = None, 
        depth: int = 0, 
        parent: "BaseBlock | None" = None, 
        dedent: bool = True
    ):
        super().__init__(content, tags, style, depth, parent, dedent)
        self.id = id or str(uuid.uuid4())
        self.name = name
        self.model = model or "gpt-4o"
        self.run_id = run_id
        self.role = role
        self.tool_calls = tool_calls or []
        self.usage = LlmUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
    
    
    @classmethod
    def from_block(
        cls,
        block: BaseBlock, 
        role: BlockRole = "user", 
        name: str | None = None, 
        model: str | None = None, 
        run_id: str | None = None, 
    ) -> "LLMBlock":
        return cls(
            content=block.content,
            role=role,
            model=model,
            run_id=run_id,
            name=name,
        )