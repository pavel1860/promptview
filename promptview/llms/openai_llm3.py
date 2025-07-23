from typing import List, Type
import openai
import os

from pydantic import BaseModel
from promptview.block.block7 import Block, Chunk
from promptview.block.util import LLMEvent, ToolCall
from promptview.llms.llm2 import LLMStream, LlmConfig
from openai.types.chat import ChatCompletionMessageParam

from promptview.utils.model_utils import schema_to_function



class OpenAiLLM(LLMStream):
    name: str = "OpenAiLLM"    
    # client: OpenAiLlmClient = Field(default_factory=OpenAiLlmClient)
    # client: openai.AsyncClient = Field(default_factory=lambda: openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY")))
    model: str | None = "gpt-4o"
    models = ["gpt-4o", "gpt-4o-mini"]
    
    
    def __init__(self):
        super().__init__()
        self.client = openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY"))
    
    def to_message(self, content: str, role: str, tool_calls: List[ToolCall] | None = None, tool_call_id: str | None = None, name: str | None = None) -> ChatCompletionMessageParam:
        message = {
            "role": role or "user",
            "content": content,
        }
        if tool_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call.id,
                        "type": "function",
                        "function": {
                            # "arguments": json.dumps(action_call.action.model_dump()),
                            "arguments": tool_call.to_json(),
                            "name": tool_call.name
                        }                      
                } for tool_call in tool_calls
            ]
        if tool_call_id:
            message["tool_call_id"] = tool_call_id
        if name:
            message["name"] = name        
        return message
    
    def to_tool(self, tool: Type[BaseModel]) -> dict:
        schema = schema_to_function(tool)
        return schema
    
    async def run(self):
        messages = [
            self.to_message(b.render(), role=b.role or "user", tool_calls=b.tool_calls, tool_call_id=b.id)
            for b in self.blocks.children
        ]
        llm_tools = None
        tool_choice = None
        if self.tools:
            llm_tools = [self.to_tool(tool) for tool in self.tools]        
            tool_choice = self.config.tool_choice

        try:       
            res_stream = await self.client.chat.completions.create(
                    messages=messages,
                    tools=llm_tools,
                    model=self.config.model,
                    tool_choice=tool_choice,
                    stream=True,
                    logprobs=True,                
                )
            
            block = Block(sep="")
            yield LLMEvent(type="stream_start")
            async for chunk in res_stream:
                if chunk.choices[0].delta:
                    choice = chunk.choices[0]
                    if choice.finish_reason:
                        break
                    content = choice.delta.content
                    try:
                        if choice.logprobs and choice.logprobs.content:                
                            logprob = choice.logprobs.content[0].logprob
                        else:
                            logprob = 0  
                    except:
                        raise ValueError("No logprobs")        
                    c = Chunk(content, logprob=logprob)
                    block.add_content(c)
                    yield c
            yield LLMEvent(type="stream_success")
            yield block
        except Exception as e:
            yield LLMEvent(type="stream_error", data={"error": str(e)})
            raise e
