from abc import abstractmethod
import json
from typing import Any, List, Type
from .llm3 import LLM
from pydantic import Field, BaseModel
from .utils.action_manager import Actions
# from ..prompt.block import BaseBlock, ResponseBlock
from ..prompt import Block, BaseBlock, LLMBlock, ToolCall
import openai
import os




    

class OpenAiLLM(LLM):
    name: str = "OpenAiLLM"    
    # client: OpenAiLlmClient = Field(default_factory=OpenAiLlmClient)
    client: openai.AsyncClient = Field(default_factory=lambda: openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY")))
    model: str = "gpt-4o"
    
    
    

    def to_message(self, block: BaseBlock | LLMBlock | Block):
        if not isinstance(block, LLMBlock):
            if isinstance(block, BaseBlock):
                block = LLMBlock.from_block(block)
            elif isinstance(block, Block):
                block = LLMBlock.from_block(block.root)
                        
        if block.role == "user" or block.role == "system":
            return {
                "role": block.role, # type: ignore
                "content": block.render(),
            }
        elif block.role == "assistant":
            oai_msg: dict[str, Any] = {"role": block.role}
            if block.tool_calls:
                tool_calls = []
                for tool_call in block.tool_calls:
                    tool_calls.append({
                    "id": tool_call.id,
                        "type": "function",
                        "function": {
                            # "arguments": json.dumps(action_call.action.model_dump()),
                            "arguments": tool_call.to_json(),
                            "name": tool_call.name
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
                "tool_call_id": block.uuid,
                "role": "tool",
                "content": block.render()
            }
            if block.name:
                oai_msg["name"] = block.name
            return oai_msg
        else:
            raise ValueError(f"Invalid block role: {block.role}")
      
    # def to_chat(self, blocks: BlockStream) -> List[BaseBlock]:
    #     return blocks.get([
    #         {
    #             "content": [
    #                 "background",
    #                 "task",     
    #                 "rules",
    #             ],
    #             "role": "system"
    #         },            
    #         "history",
    #         "user_message"
    #     ])
        
        
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
                    ToolCall(
                        id=tool_call.id,
                        name=tool_call.function.name,
                        tool=action_instance
                    ))
                
                
        response_block = Block.message(
            content=output.content,
            role="assistant",
            tool_calls=tool_calls,
        )
        return response_block
        
        response_block = LLMBlock(
            output.content,
            role="assistant",
            # id=response.id,
            # model=response.model,
            # content=output.content,
            # action_calls=tool_calls, 
            # raw=response,
            # usage=LlmUsage(
            #     prompt_tokens=response.usage.prompt_tokens,
            #     completion_tokens= response.usage.completion_tokens,
            #     total_tokens= response.usage.total_tokens,
            # )
        )
        return response_block