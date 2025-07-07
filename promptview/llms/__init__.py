from .azure_llm import AzureOpenAiLLM
from .openai_llm2 import OpenAiLLM
from .legacy.phi_llm import PhiLLM
from .llm import LLM, OutputModel
from .exceptions import LlmError, LLMToolNotFound
from .types import ToolChoice, ErrorMessage
from .utils.completion_parsing import PromptParsingException

LLM.register(OpenAiLLM, default_model="gpt-4o")



__all__ = [
    "PhiLLM", 
    "LLM", 
    "LlmError", 
    "LLMToolNotFound", 
    "PromptParsingException", 
    "ToolChoice", 
    "ErrorMessage",
    "OutputModel",
]