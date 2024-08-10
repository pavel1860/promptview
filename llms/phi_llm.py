from typing import List

from pydantic import Field
from promptview.llms.clients.phi_llm_client import PhiLlmClient
from promptview.llms.llm import LLM


class PhiLLM(LLM):
    name: str = "PhiLLM"
    stop_sequences: List[str]=["Instruct"]
    client: PhiLlmClient = Field(default_factory=PhiLlmClient)
    model: str = "microsoft/phi-2"

