
from typing import List, Literal
from promptview.model.fields import ModelField
from promptview.model.model import Model
from promptview.model.version_control_models import TurnModel
from promptview.block.block import Blockable, ToolCall, Block
import copy



class BlockModel(TurnModel):
    block: dict = ModelField(default_factory=dict)
    role: Literal["user", "assistant", "system", "tool"] = ModelField(default="user")
    platform_id: str | None = ModelField(default=None)
    tool_calls: List[ToolCall] = ModelField(default=[])
    model: str | None = ModelField(default=None)
    run_id: str | None = ModelField(default=None)
    
    
    
    @classmethod
    def from_block(cls, target: "Block | Blockable") -> "BlockModel":
        if not isinstance(target, Block):
            if hasattr(target, "block"):
                target = target.block()
            else:
                raise ValueError("Invalid target")
        return cls(
            block=target.model_dump(),
            role=target.role,
            platform_id=target.id,
            tool_calls=target.tool_calls,
            model=target.model,
            run_id=target.run_id,
        )
    
        
    def _payload_dump(self, *args, **kwargs):
        res = super()._payload_dump(*args, **kwargs)
        if self.tool_calls:
            res["tool_calls"] = [tool.model_dump() for tool in self.tool_calls]
        return res
        
    def to_block(self) -> Block:                
        block = Block.model_validate(copy.deepcopy(self.block))
        return block