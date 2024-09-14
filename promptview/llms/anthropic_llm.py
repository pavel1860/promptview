from pydantic import Field
from promptview.llms.clients.anthropic_client import AnthropicLlmClient
from promptview.llms.llm2 import LLM


class AnthtropicLLM(LLM):
    model: str = "claude-3-5-sonnet-20240620"
    name: str = "AnthropicLLM"
    client: AnthropicLlmClient = Field(default_factory=AnthropicLlmClient)
