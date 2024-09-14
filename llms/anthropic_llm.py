from pydantic import Field
from promptview.llms.clients.anthropic_client import AnthropicLlmClient
from promptview.llms.llm2 import LLM


class AnthtropicLLM(LLM):
    client: AnthropicLlmClient = Field(default_factory=AnthropicLlmClient)
