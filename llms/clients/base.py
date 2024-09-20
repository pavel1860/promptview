from typing import Any, List
from pydantic import BaseModel
import pickle


class BaseLlmClient(BaseModel):
    client: Any
    
    async def complete(self, msgs, **kwargs):
        raise NotImplementedError
    
    
    
    def serialize_messages(self, messages: List[BaseModel], run_id: str):
        with open(f"tmp/messages_{run_id}.pkl", "wb") as f:
            pickle.dump(messages, f)
    