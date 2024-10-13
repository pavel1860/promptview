import pickle
from abc import abstractmethod
from datetime import datetime
from typing import Any, AsyncGenerator, List

from ..interpreter.messages import AIMessage, MessageChunk
from pydantic import BaseModel


class BaseLlmClient(BaseModel):
    client: Any
    
    async def complete(self, *args, **kwargs) -> AIMessage:
        raise NotImplementedError
    
    
    async def stream(self, *args, **kwargs) -> AsyncGenerator[MessageChunk, None]:
        yield MessageChunk(id="test", content="streaming not implemented")
        raise NotImplementedError
    
    def serialize_messages(self,  run_id: str, messages: List[BaseModel], response: BaseModel | None = None):
        date_str = datetime.now().strftime("%d_%H-%M")
        obj = {
            "run_id": run_id,
            "messages": messages,
            "response": response
        }
        with open(f"tmp/messages_{date_str}_{run_id}.pkl", "wb") as f:
            pickle.dump(obj, f)
    