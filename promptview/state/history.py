
from typing import List
from promptview.llms.messages import BaseMessage, filter_action_calls, validate_msgs
import asyncio







class History:
    
    def __init__(self, add_actions=False) -> None:
        self.history: List[BaseMessage] = []
        self.add_actions = add_actions
        self.contained_id = set([])
        
                
    def add(self, context, message: BaseMessage, run_id: str, prompt: str):
        if message.id is None:
            raise Exception("message id is None")
        if message.id not in self.contained_id:
            self.history.append(message)
            asyncio.create_task(self.save(context, message, run_id, prompt))
    
    
    async def init(self, context):
        messages = await self.load(context)
        for message in messages:
            if not isinstance(message, BaseMessage):
                raise Exception(f"message {type(message)} is not an instance of BaseMessage")
        self.history = messages
                
    # def add_many(self, messages: List[BaseMessage]):
        # self.history.extend(messages)
        
    def get(self, from_idx=1, to_idx=None, safe=False):
        """
        get the last n messages
        safe: remove action messages that are not connected to any tool calls
        """
        if to_idx is  not None:
            messages = self.history[-from_idx: -to_idx]
        else:
            messages = self.history[-from_idx:]
        
        if safe:
            messages = filter_action_calls(messages)
        return messages
    
    def clear(self):
        self.history = []
    
    def last(self):
        return self.history[-1]
    

    async def load(self, context):
        return self.history
    
    async def save(self, context, message: BaseMessage, run_id: str, prompt: str):
        return 