
from typing import List, Literal
from promptview.model2.fields import ModelField
from promptview.model2.model import Model
from promptview.model2.version_control_models import TurnModel
from promptview.prompt.block6 import ToolCall, Block




class BlockModel(TurnModel):
    block: dict = ModelField(default_factory=dict)
    role: Literal["user", "assistant", "system"] = ModelField(default="user")
    platform_id: str | None = ModelField(default=None)
    tool_calls: List[ToolCall] = ModelField(default=[])
    model: str | None = ModelField(default=None)
    run_id: str | None = ModelField(default=None)
    
    
    
    @classmethod
    def from_block(cls, block: "Block") -> "BlockModel":
        return cls(
            block=block.model_dump(),
            role=block.role,
            platform_id=block.id,
            tool_calls=block.tool_calls,
            model=block.model,
            run_id=block.run_id,
        )
    
        
    def _payload_dump(self, *args, **kwargs):
        res = super()._payload_dump(*args, **kwargs)
        if self.tool_calls:
            res["tool_calls"] = [tool.model_dump() for tool in self.tool_calls]
        return res
        
    def to_block(self) -> Block:                
        block = Block.model_validate(self.block)
        return block