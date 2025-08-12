from datetime import datetime
from typing import List, Type
import openai
import os

from pydantic import BaseModel
from promptview.block.block7 import Block, BlockList, Chunk
from promptview.block.util import LLMEvent, ToolCall
from promptview.context.execution_context import ExecutionContext
from promptview.llms.llm2 import LLMStream, LlmConfig
from openai.types.chat import ChatCompletionMessageParam


from promptview.utils.model_utils import schema_to_function



class OpenAiLLM(LLMStream):
    name: str = "OpenAiLLM"    
    # client: OpenAiLlmClient = Field(default_factory=OpenAiLlmClient)
    # client: openai.AsyncClient = Field(default_factory=lambda: openai.AsyncClient(api_key=os.getenv("OPENAI_API_KEY")))
    model: str | None = "gpt-4o"
    models = ["gpt-4o", "gpt-4o-mini"]
    
    
    def __init__(self, blocks: BlockList, config: LlmConfig, tools: List[Type[BaseModel]] | None = None, model: str | None = None):
        super().__init__(blocks, config, tools, model)
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
    
    async def stream(self):
        messages = [
            self.to_message(b.render(), role=b.role or "user", tool_calls=b.tool_calls, tool_call_id=b.id)
            for b in self.blocks
        ]
        llm_tools = None
        tool_choice = None
        if self.tools:
            llm_tools = [self.to_tool(tool) for tool in self.tools]        
            tool_choice = self.llm_config.tool_choice

        # try:       
        res_stream = await self.client.chat.completions.create(
                messages=messages,
                tools=llm_tools,
                model=self.llm_config.model,
                tool_choice=tool_choice,
                stream=True,
                logprobs=True,                
            )
                    
        async for chunk in res_stream:                
            if chunk.choices[0].delta:
                choice = chunk.choices[0]                   
                content = choice.delta.content
                if content is None:
                    continue
                try:
                    if choice.logprobs and choice.logprobs.content:                
                        logprob = choice.logprobs.content[0].logprob
                    else:
                        logprob = 0  
                except:
                    raise ValueError("No logprobs")        
                blk_chunk = Block(content, logprob=logprob)
                yield blk_chunk
                    
                    
        # except Exception as e:
            # yield = Block(str(e))
            # event = Event(type="stream_error", payload=block, timestamp=int(datetime.now().timestamp()), request_id=request_id)
            # yield event
            # raise e
