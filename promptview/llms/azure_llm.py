
from typing import List, Optional, Tuple, Type

from promptview.llms.clients.azure_client import AzureOpenAiLlmClient
from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.llm import LLM
from promptview.llms.interpreter.messages import (ActionMessage, AIMessage, BaseMessage,
                                      HumanMessage, SystemMessage)
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import ViewBlock
from pydantic import BaseModel
from promptview.templates.action_template import system_action_view

class AzureOpenAiLLM(LLM):
    name: str = "AzureOpenAiLLM"
    client: BaseLlmClient
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    api_version: Optional[str] = "2023-12-01-preview"
    azure_endpoint: Optional[str] = None
    azure_deployment: Optional[str] = None
    

    def __init__(self, api_key, api_version, azure_endpoint, azure_deployment, **kwargs):
        client = AzureOpenAiLlmClient(
            api_key=api_key,
            api_version=api_version,
            azure_endpoint=azure_endpoint,
            azure_deployment=azure_deployment,            
        )
        super().__init__(
            client= client,            
            **kwargs
        )

    
    def transform(self, root_block: ViewBlock, actions: Actions | List[Type[BaseModel]] | None = None, **kwargs) -> Tuple[List[BaseMessage], Actions]:
        messages = []
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        actions.extend(root_block.find_actions())
        system_block = root_block.first(role="system", depth=1)
        if system_block and actions:
            system_block.push(system_action_view(actions))
        for block in root_block.find(depth=1): 
            content = self.render_block(block, **kwargs)
            if block.role == 'user':
                messages.append(HumanMessage(id=block.uuid, content=content))
            elif block.role == 'assistant':
                messages.append(AIMessage(id=block.uuid, content=content, action_calls=block.action_calls))
            elif block.role == 'system':
                messages.append(SystemMessage(id=block.uuid, content=content))
            elif block.role == 'tool':
                messages.append(ActionMessage(id=block.uuid, content=content))
            else:
                raise ValueError(f"Unsupported role: {block.role}")
        
        return messages, actions