


import asyncio
import random
import re

import openai
from promptview.llms.clients.base import BaseLlmClient

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

    async def complete(self, msgs, tools=None, retries=10, run_id: str| None=None, **kwargs):
        kwargs = {k: v for k, v in kwargs.items() if azure_arg_filters(k, v)}            
        msgs = self.preprocess(msgs)
        await rate_limit_event.wait()
        for i in range(retries):
            try:
                openai_completion = await self.client.chat.completions.create(
                    messages=msgs,
                    tools=tools,
                    **kwargs
                )
                return openai_completion
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
