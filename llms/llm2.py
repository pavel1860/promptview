from typing import List
from pydantic import BaseModel
from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.interpreter import LlmInterpreter
from promptview.llms.messages import BaseMessage


class LLM(BaseModel, LlmInterpreter):
    client: BaseLlmClient 
       
    
    async def complete(self, messages: List[BaseMessage], actions=None):
        response = await self.client.complete(messages, actions=actions)
        return response  
        
    async def __call__(self, views):
        messages, actions = self.run_transform(views)
        return await self.complete(messages, actions)
