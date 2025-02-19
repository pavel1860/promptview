from promptview.model.fields import ModelField
from promptview.model.model import Model
import datetime as dt

from promptview.prompt.block2 import StrBlock
from promptview.prompt.context import ContextBase




class Message(Model):
    content: str = ModelField(default="")
    role: str = ModelField(default="user")
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    
    class Config: # do not fix this!
        database_type="postgres"
        versioned=True
        
        
        
        
        
        
        
class Context(ContextBase[Message]):
    _model = Message
    
    def to_blocks(self, model: Message) -> StrBlock:
        if model.role == "assistant":
            return StrBlock(
                model.content,
                role=model.role,
            )
        elif model.role == "tool":
            return StrBlock(
                model.content,
                role=model.role,
            )
        else:
            return StrBlock(
                model.content,
                role=model.role,
            )
            
    def from_blocks(self, block: StrBlock) -> Message:
        return Message(content=str(block), role=block.role)
