from typing import Any
from pydantic import BaseModel


class BaseLlmClient(BaseModel):
    client: Any
    async def complete(self, msgs, **kwargs):
        raise NotImplementedError