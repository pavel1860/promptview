


import asyncio
import random
import re
from typing import Type

import openai
from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.messages import (ActionCall, AIMessage, BaseMessage,
                                      LlmChunk, LlmUsage, validate_msgs)
from promptview.llms.types import ToolChoice
from promptview.llms.utils.action_manager import Actions
from pydantic import BaseModel

rate_limit_event = asyncio.Event()
rate_limit_event.set()


async def check_event_status(event, name):
    if event.is_set():
        print(f'{name} found the event is SET. openai api is free for requests')
    else:
        print(f'{name} found the event is NOT SET. RATE LIMIT HIT. waiting for event to be set.')



def azure_arg_filters(key, value):
    if key == "parallel_tool_calls":
        return False
    elif key == "tool_choice" and value == "required":
        return False
    return True


def get_delay_from_exception(e: Exception) -> int:
    if "retry after" in str(e):
        match = re.search(r"retry after (\d+) seconds", str(e))
        if match:
            random_buffer = random.randrange(1, 10)
            delay = int(match.group(1)) + random_buffer
            return delay
    return 60

class AzureOpenAiLlmClient(BaseLlmClient):


    def __init__(self, api_key: str, api_version: str, azure_endpoint:str, azure_deployment: str):
        super().__init__(
            client=openai.AsyncAzureOpenAI(
                    api_key=api_key,
                    api_version=api_version,
                    azure_endpoint=azure_endpoint,
                    azure_deployment=azure_deployment,
                ) 
        )

    def preprocess(self, msgs):
        return [msg.to_openai() for msg in msgs if msg.is_valid()]

    async def complete(
        self, 
        messages: list[BaseMessage],
        actions: Actions | list[Type[BaseModel]]=[], 
        model="gpt-4o",
        tool_choice: ToolChoice | BaseModel | None = None,
        retries=10, 
        run_id: str| None=None, 
        **kwargs
    ):
        kwargs = {k: v for k, v in kwargs.items() if azure_arg_filters(k, v)}        
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        tools = actions.to_openai()
        azure_messages = [msg.to_openai() for msg in validate_msgs(messages)]
        if isinstance(tool_choice, BaseModel):
            azure_tool_choice =  {"type": "function", "function": {"name": tool_choice.__class__.__name__}}            
        else:
            azure_tool_choice = tool_choice
        await rate_limit_event.wait()
        for i in range(retries):
            try:
                openai_completion = await self.client.chat.completions.create(
                    messages=azure_messages,
                    tools=tools,
                    model=model,
                    tool_choice=azure_tool_choice,
                    **kwargs
                )
                return self.parse_output(openai_completion, actions)
            except openai.RateLimitError as e:
                print("hit rate limit")
                sleep_time = get_delay_from_exception(e)
                rate_limit_event.clear()
                await asyncio.sleep(sleep_time)
                rate_limit_event.set()
                continue
            except Exception as e:
                print("other exception", e)
                raise e
            
            
    async def stream(
        self, 
        messages: list[BaseMessage],
        actions: Actions | list[Type[BaseModel]]=[], 
        model="gpt-4o",
        tool_choice: ToolChoice | BaseModel | None = None,
        retries=10, 
        run_id: str| None=None, 
        **kwargs
    ):
        kwargs = {k: v for k, v in kwargs.items() if azure_arg_filters(k, v)}        
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        tools = actions.to_openai()
        azure_messages = [msg.to_openai() for msg in validate_msgs(messages)]
        if isinstance(tool_choice, BaseModel):
            azure_tool_choice =  {"type": "function", "function": {"name": tool_choice.__class__.__name__}}            
        else:
            azure_tool_choice = tool_choice
        await rate_limit_event.wait()
        for i in range(retries):
            try:
                openai_stream = await self.client.chat.completions.create(
                    messages=azure_messages,
                    tools=tools,
                    model=model,
                    tool_choice=azure_tool_choice,                    
                    stream=True,
                    **kwargs
                )
                async for chunk in openai_stream:
                    if chunk.choices:
                        if chunk.choices[0].finish_reason == "stop":
                            yield LlmChunk(
                                id=chunk.id,
                                content=chunk.choices[0].delta.content,
                                did_finish= True
                            )
                            return                        
                        elif chunk.choices[0].delta.content is not None:
                            yield LlmChunk(
                                id=chunk.id,
                                content=chunk.choices[0].delta.content,
                            )
                return
            except openai.RateLimitError as e:
                print("hit rate limit")
                sleep_time = get_delay_from_exception(e)
                rate_limit_event.clear()
                await asyncio.sleep(sleep_time)
                rate_limit_event.set()
                continue
            except Exception as e:
                print("other exception", e)
                raise e
        
            
            
    def parse_output(self, response, actions: Actions):
        try:
            output = response.choices[0].message
            tool_calls = []
            if output.tool_calls:
                for tool_call in output.tool_calls:
                    action_instance = actions.from_openai(tool_call)
                    # tool_calls.append({"id": tool_call.id, "action": action_instance})
                    tool_calls.append(
                        ActionCall(
                            id=tool_call.id,
                            name=tool_call.function.name,
                            action=action_instance
                        ))
            ai_message = AIMessage(
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
            return ai_message
        except Exception as e:
            raise e
        
        
    

    