from abc import abstractmethod
import json
from typing import List, Type
# from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.clients.openai_client import OpenAiLlmClient
from promptview.llms.llm3 import LLM, BaseLlmClient
from pydantic import Field, BaseModel
from promptview.llms.messages import ActionCall, LlmUsage
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.block import BaseBlock, ResponseBlock
from promptview.prompt.context import CtxBlocks
import openai
import os


    

class OpenAiLLM(LLM):
    name: str = "OpenAiLLM"    
    # client: OpenAiLlmClient = Field(default_factory=OpenAiLlmClient)
    client: openai.AsyncClient = Field(default_factory=lambda: openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY")))
    model: str = "gpt-4o"

    
    
    def to_message(self, block: BaseBlock):
        print(block.role)
        if block.role == "user" or block.role == "system":
            return {
                "role": block.role, # type: ignore
                "content": block.render(),
            }
        elif block.role == "assistant":
            oai_msg: dict[str, Any] = {"role": block.role}
            if block.action_calls:
                tool_calls = []
                for action_call in block.action_calls:
                    tool_calls.append({
                    "id": action_call.id,
                        "type": "function",
                        "function": {
                            # "arguments": json.dumps(action_call.action.model_dump()),
                            "arguments": action_call.action.model_dump_json() if isinstance(action_call.action, BaseModel) else json.dumps(action_call.action),
                            "name": action_call.name
                        }                      
                    })
                oai_msg["tool_calls"] = tool_calls
            else:
                oai_msg["content"] = block.render()
            if block.name:
                oai_msg["name"] = block.name
            return oai_msg
        elif block.role == "tool":
            oai_msg = {
                "tool_call_id": block.tool_call_id,
                "role": "tool",
                "content": block.render()
            }
            if block.name:
                oai_msg["name"] = block.name
            return oai_msg
        
    def to_chat(self, ctx: CtxBlocks) -> List[BaseBlock]:
        return ctx.get_blocks([
            {
                "content": [
                    "background",
                    "task",     
                    "rules",
                ],
                "role": "system"
            },            
            "history"
        ])
        
        
    def to_tools(self, actions: List[Type[BaseModel]]) -> List[dict] | None:
        return Actions(actions).to_openai()
        
    async def complete(
        self, 
        messages: List[dict],   
        tools: List[dict] | None = None, 
        model: str = "gpt-4o", 
        tool_choice: str | None = None, 
        **kwargs
    ):
        openai_completion = await self.client.chat.completions.create(
            messages=messages,
            tools=tools,
            model=model,
            tool_choice=tool_choice,
            # **kwargs
        )
        return openai_completion

        
    def parse_response(self, response: openai.types.chat.chat_completion.ChatCompletion, actions: List[Type[BaseModel]] | None):
        output = response.choices[0].message
        tool_calls = []
        if output.tool_calls and actions:
            action_parser = Actions(actions)
            for tool_call in output.tool_calls:
                action_instance = action_parser.from_openai(tool_call)
                # tool_calls.append({"id": tool_call.id, "action": action_instance})
                tool_calls.append(
                    ActionCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        action=action_instance
                    ))
        response_block = ResponseBlock(
            id=response.id,
            model=response.model,
            content=output.content,
            action_calls=tool_calls, 
            raw=response,
            usage=LlmUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens= response.usage.completion_tokens,
                total_tokens= response.usage.total_tokens,
            )
        )
        return response_block