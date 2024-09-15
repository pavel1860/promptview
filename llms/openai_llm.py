



from typing import Optional
from pydantic import Field
from promptview.llms.clients.openai_client import OpenAiLlmClient
from promptview.llms.llm2 import LLM


class OpenAiLLM(LLM):
    name: str = "OpenAiLLM"    
    client: OpenAiLlmClient = Field(default_factory=OpenAiLlmClient)
    model: str = "gpt-4o"
    api_key: Optional[str] = None