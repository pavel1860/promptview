from typing import List, Tuple
from pydantic import BaseModel, Field
from promptview.llms.clients.anthropic_client import AnthropicLlmClient
from promptview.llms.llm2 import LLM
from promptview.llms.messages import AIMessage, ActionMessage, BaseMessage, HumanMessage, SystemMessage
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import ViewBlock
from promptview.templates.action_template import system_action_view


class AnthropicLLM(LLM):
    model: str = "claude-3-5-sonnet-20240620"
    name: str = "AnthropicLLM"
    client: AnthropicLlmClient = Field(default_factory=AnthropicLlmClient)

    
    def transform(self, root_block: ViewBlock, actions: Actions | List[BaseModel] | None = None, **kwargs) -> Tuple[List[BaseMessage], Actions]:
        messages = []
        system_content = ""
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        actions.extend(root_block.find_actions())
        system_block = root_block.first(role="system", depth=1)
        if system_block:
            system_block.push(system_action_view(actions))
        for block in root_block.find(depth=1): 
            content = self.render_block(block, **kwargs)
            if block.role == 'user':
                messages.append(HumanMessage(id=block.uuid, content=content))
            elif block.role == 'assistant':
                messages.append(AIMessage(id=block.uuid, content=content, action_calls=block.action_calls))
            elif block.role == 'system':
                system_content += content + "\n"
                # messages.append(SystemMessage(id=block.uuid, content=content))
            elif block.role == 'tool':
                messages.append(ActionMessage(id=block.uuid, content=content))
            else:
                raise ValueError(f"Unsupported role: {block.role}")
        if system_content:
            messages = [SystemMessage(id=block.uuid, content=system_content)] + messages
        return messages, actions
    
    def transform2(self, root_block: ViewBlock, actions: Actions | List[BaseModel] | None = None, **kwargs) -> Tuple[List[BaseMessage], Actions]:
        system_content = ""
        messages = []
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        for block in root_block.find(depth=1):
            content = self.render_block(block) # need to replace with render
            if block.role == 'user':
                messages.append(HumanMessage(id=block.uuid, content=content))
            elif block.role == 'assistant':                
                if block.action_calls:
                    content_blocks = [
                        {
                            "type": "text",
                            "content": content
                        }
                    ]                
                    for action_call in block.action_calls:
                        tool_result = root_block.first(role='tool', uuids=[action_call.id])
                        if tool_result:
                            content_blocks.append({
                                "type": "tool_use",
                                "id": action_call.id,
                                "name": action_call.name,
                                "input": action_call.action.model_dump()
                            })                                            
                    messages.append(
                        AIMessage(
                            content='',
                            id=block.uuid,
                            content_blocks=[
                                {
                                    "type": "text",
                                    "content": content
                                }
                            ]
                        ))
                else:
                    messages.append(AIMessage(id=block.uuid, content=content))
            elif block.role == 'system':        
                system_content += content + "\n"
            elif block.role == 'tool':
                messages.append(HumanMessage(
                    id=block.uuid, 
                    content="",
                    content_blocks=[{
                        "type": "tool_result",
                        "tool_use_id": block.uuid,
                        "content": content  
                    }]
                ))        
        if system_content:
            messages = [SystemMessage(id=block.uuid, content=system_content)] + messages        
        return messages, actions