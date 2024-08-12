
import os

import openai
from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.messages import validate_msgs

class OpenAiLlmClient(BaseLlmClient):


    def __init__(self, api_key=None):
        super().__init__(
            client = openai.AsyncClient(
                api_key=api_key or os.getenv("OPENAI_API_KEY")
            )
        )

    def preprocess(self, msgs):
        return [msg.to_openai() for msg in validate_msgs(msgs)]
        # return [msg.to_openai() for msg in msgs if msg.is_valid()]

    async def complete(self, msgs, tools=None, run_id: str | None=None, **kwargs):
        msgs = self.preprocess(msgs)
        openai_completion = await self.client.chat.completions.create(
            messages=msgs,
            tools=tools,
            **kwargs
        )
        return openai_completion
