from typing import Any, AsyncGenerator, Dict, List, Literal, Type, Unpack
from pydantic import BaseModel, Field



from promptview.block.block7 import Block, BlockContext, BlockPrompt, BlockList, Chunk
from promptview.block.util import StreamEvent
from promptview.prompt.stream2 import GeneratorFrame, StreamController
from promptview.prompt.events import Event, EventParams



ToolChoice = Literal['auto', 'required', 'none']

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



    

class LLMStream(StreamController):
    blocks: BlockList
    llm_config: LlmConfig
    tools: List[Type[BaseModel]] | None = None
    model: str | None = None
    models: List[str] = []
    
    
    def __init__(self):
        super().__init__(self.__class__.__name__, accumulator=lambda : BlockList([], style="list-stream"))
        
    async def stream(self) -> AsyncGenerator[Any, None]:
        pass
        yield
    
    

    def __call__(self, blocks: BlockList, config: LlmConfig, tools: List[Type[BaseModel]] | None = None):
        self.blocks = blocks
        self.llm_config = config
        self.tools = tools
        return self
    
    
    def to_event(self, ctx: GeneratorFrame, value: Any) -> Event:
        if not ctx.emitted_start:
            ctx.emitted_start = True
            llm_payload = {
                "config": self.llm_config.model_dump(),
                "tools": [tool.model_dump() for tool in self.tools] if self.tools else None,
                "model": self.model,
                "blocks": [b.render() for b in self.blocks]
            }
            return Event(type="stream_start", span=self._name, payload=llm_payload, index=0)
        elif ctx.exhausted:
            return Event(type="stream_end", span=self._name, payload=ctx.accumulator, index=ctx.index)
        else:
            return Event(type="message_delta", span=self._name, payload=value, index=ctx.index)
    
    
    
    
    
    
    
class LLM():
    
    _model_registry: Dict[str, Type[LLMStream]] = {}
    _default_model: str | None = None
        
    
    
    @classmethod
    def register(cls, model_cls: Type[LLMStream], default_model: str | None = None) -> Type[LLMStream]:
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
        llm = llm_cls()
        return llm

    def __call__(
        self,        
        *blocks: Block | BlockContext |BlockList | BlockPrompt | str,
        model: str | None = None,
        config: LlmConfig | None = None,
    ) -> LLMStream:                                
        if isinstance(blocks, str):
            llm_blocks = BlockList([Block(blocks)])
        elif isinstance(blocks, tuple):
            llm_blocks = BlockList()
            for b in blocks:
                if isinstance(b, str):
                    llm_blocks.append(Block(b))
                else:
                    llm_blocks.append(b)
        elif isinstance(blocks, Block):
            llm_blocks = BlockList([blocks])
        elif isinstance(blocks, BlockPrompt):
            llm_blocks = BlockList([blocks.root])
        elif isinstance(blocks, BlockList):
            llm_blocks = blocks        
        else:
            raise ValueError(f"Invalid blocks type: {type(blocks)}")
        
        llm_ctx = self._get_llm(model)
        config = config or LlmConfig(model=llm_ctx.model)
        return llm_ctx(llm_blocks, config)
    # def __call__(
    #     self,        
    #     blocks: BlockContext |BlockList | Block | BlockPrompt | str,
    #     model: str | None = None,
    #     config: LlmConfig | None = None,
    # ) -> LLMStream:                        
    #     if isinstance(blocks, str):
    #         llm_blocks = BlockList([Block(blocks)])
    #     elif isinstance(blocks, Block):
    #         llm_blocks = BlockList([blocks])
    #     elif isinstance(blocks, BlockPrompt):
    #         llm_blocks = BlockList([blocks.root])
    #     elif isinstance(blocks, BlockList):
    #         llm_blocks = blocks        
    #     else:
    #         raise ValueError(f"Invalid blocks type: {type(blocks)}")
        
    #     llm_ctx = self._get_llm(model)
    #     config = config or LlmConfig(model=llm_ctx.model)
    #     return llm_ctx(llm_blocks, config)
