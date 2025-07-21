from typing import AsyncGenerator, Dict, List, Type
from pydantic import BaseModel, Field
from pydantic.types import ToolChoice


from promptview.block.block7 import Block
from promptview.block.util import StreamEvent
from promptview.prompt.stream import StreamController


class LlmConfig(BaseModel):
    model: str | None = Field(default=None, description="The model to use")
    temperature: float = Field(default=0, ge=0, le=1, description="The temperature of the response")
    max_tokens: int | None = Field(default=None, ge=0, description="The maximum number of tokens in the response")
    stop_sequences: List[str] | None = Field(default=None, description="The stop sequences of the response")
    stream: bool = Field(default=False, description="If the response should be streamed")
    logit_bias: Dict[str, int] | None = Field(default=None, description="The logit bias of the response")
    top_p: float = Field(default=1, ge=0, le=1, description="The top p of the response")
    presence_penalty: float | None = Field(default=None, ge=-2, le=2, description="The presence penalty of the response")
    logprobs: bool | None = Field(default=None, description="If the logprobs should be returned")
    seed: int | None = Field(default=None, description="The seed of the response")
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2, description="The frequency penalty of the response")
    tools: List[Type[BaseModel]] | None = Field(default=None, description="The tools of the response")
    retries: int = Field(default=3, ge=1, description="The number of retries")
    parallel_tool_calls: bool = Field(default=False, description="If the tool calls should be parallel")
    tool_choice: ToolChoice | None = Field(default=None, description="The tool choice of the response")




class LLMStream(StreamController[StreamEvent]):
    pass
    
    
    
    
    
    
    
    
class LLM():
    
    _model_registry: Dict[str, Type[LLMStream]] = {}
    _default_model: str | None = None
    
    
    @classmethod
    def register(cls, model_cls: Type[LLMStream], default_model: str | None = None) -> Type[LlmContext]:
        """Decorator to register a new LLM model implementation"""
        if model_cls.__name__ in cls._model_registry:
            raise ValueError(f"Model {model_cls.__name__} is already registered")
        for model in model_cls.models:
            cls._model_registry[model] = model_cls
        if default_model:
            cls._default_model = default_model
        return model_cls
    
    @classmethod
    def _get_llm(cls, model: str | None = None) -> LLMStream:
        """Get a registered model by name"""
        if model is None:
            if cls._default_model is None:
                raise ValueError("No default model is set")
            model = cls._default_model
        if model not in cls._model_registry:
            raise KeyError(f"Model {model} is not registered")        
        llm_cls = cls._model_registry[model]
        llm = llm_cls(model)
        return llm

    
    def __call__(
        self,        
        *args: Block | str,
        model: str | None = None,
    ) -> LLMStream:                        
                        
                        
        llm_ctx = self._get_llm(model)
        return llm_ctx(ctx_blocks)
