from abc import abstractmethod
from typing import Any, Callable, Dict, Generic, List, Literal, ParamSpec, Type, TypeVar, Union, TYPE_CHECKING
import anthropic
import openai
from pydantic import BaseModel, ValidationError, Field
from promptview.llms.clients.anthropic_client import AnthropicLlmClient
# from promptview.llms.clients.base import BaseLlmClient
from promptview.llms.clients.openai_client import OpenAiLlmClient
from promptview.llms.exceptions import LLMToolNotFound
from promptview.llms.interpreter import LlmInterpreter
# from promptview.llms.llm import ToolChoice
from promptview.llms.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.tracer2 import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.block import BaseBlock, ResponseBlock

from promptview.prompt.context import BlockStream, Context
from promptview.prompt.mvc import ViewBlock




ToolChoice = Literal['auto', 'required', 'none']

LLM_CLIENT = TypeVar('LLM_CLIENT')
CLIENT_PARAMS = ParamSpec('CLIENT_PARAMS')
CLIENT_RESPONSE = TypeVar('CLIENT_RESPONSE')



class BaseLlmClient(BaseModel, Generic[LLM_CLIENT, CLIENT_RESPONSE]):
    client: LLM_CLIENT
    
    @abstractmethod
    async def complete(
        self, 
        messages: List[dict], 
        tools: List[dict], 
        model: str, 
        tool_choice: str, 
        **kwargs
    ) -> CLIENT_RESPONSE:
        ...


class LlmConfig(BaseModel):
    temperature: float | None = None
    max_tokens: int | None = None
    stop_sequences: List[str] | None = None
    stream: bool = False
    logit_bias: Dict[str, int] | None = None
    top_p: float | None = None
    presence_penalty: float | None = None
    logprobs: bool | None = None
    seed: int | None = None
    frequency_penalty: float | None = None
    
    
    
    def get_llm_args(self, **kwargs):
        model_kwargs={}
        stop_sequences = kwargs.get("stop_sequences", self.stop_sequences)
        if stop_sequences:
            model_kwargs['stop'] = stop_sequences
        logit_bias = kwargs.get("logit_bias", self.logit_bias)
        if logit_bias:            
            model_kwargs['logit_bias'] = logit_bias
        top_p = kwargs.get("top_p", self.top_p)
        if top_p:
            if top_p > 1.0 or top_p < 0.0:
                raise ValueError("top_p must be between 0.0 and 1.0")
            model_kwargs['top_p'] = top_p
        presence_penalty = kwargs.get("presence_penalty", self.presence_penalty)
        if presence_penalty:
            if presence_penalty > 2.0 or presence_penalty < -2.0:
                raise ValueError("presence_penalty must be between -2.0 and 2.0")
            model_kwargs['presence_penalty'] = presence_penalty
        frequency_penalty = kwargs.get("frequency_penalty", self.frequency_penalty)
        if frequency_penalty:
            if frequency_penalty > 2.0 or frequency_penalty < -2.0:
                raise ValueError("frequency_penalty must be between -2.0 and 2.0")
            model_kwargs['frequency_penalty'] = frequency_penalty
        temperature = kwargs.get("temperature", self.temperature)
        if temperature is not None:
            model_kwargs['temperature'] = temperature
        max_tokens = kwargs.get("max_tokens", self.max_tokens)
        if max_tokens is not None:
            model_kwargs['max_tokens'] = max_tokens

        # model = kwargs.get("model", self.model)
        # if model is not None:
        #     model_kwargs['model'] = model
        
        seed = kwargs.get("seed", self.seed)
        if seed is not None:
            model_kwargs['seed'] = seed
            
        # parallel_tool_calls = kwargs.get("parallel_tool_calls", self.parallel_tool_calls)
        # if parallel_tool_calls is not None and actions:
        #     model_kwargs['parallel_tool_calls'] = parallel_tool_calls
            
        logprobs = kwargs.get("logprobs", self.logprobs)
        if logprobs is not None:
            model_kwargs['logprobs'] = logprobs        
        return model_kwargs




class LlmExecution(BaseModel, Generic[CLIENT_PARAMS, CLIENT_RESPONSE]):
    # blocks: List[BaseBlock] = []
    ctx_blocks: BlockStream 
    # messages: List[BaseMessage] = []
    messages: List[dict] = []
    # actions: Actions = Actions()
    actions: List[Type[BaseModel]] = []
    tools: List[dict] | None = None
    model: str
    # client: BaseLlmClient
    name: str
    tool_choice: ToolChoice | None = None
    parallel_tool_calls: bool = False
    config: LlmConfig = LlmConfig()
    is_traceable: bool | None = True
    tracer_run: Tracer | None = None
    _to_tools: Callable[[list[Type[BaseModel]]], List[dict] | None] | None = None
    _complete: Callable[CLIENT_PARAMS, CLIENT_RESPONSE] | None = None
    _parse_response: Callable[[CLIENT_RESPONSE, list[Type[BaseModel]]], ResponseBlock] | None = None
    
    class Config:
        arbitrary_types_allowed = True   
    
    def __await__(self):
        return self.run_complete().__await__()
        
    
    def pick_one(self, actions: List[Type[BaseModel]]):
        self.tool_choice = "required"
        self.parallel_tool_calls = False
        self.actions = actions
        return self
    
    def pick_many(self, actions: List[Type[BaseModel]]):
        self.tool_choice = "required"
        self.parallel_tool_calls = True
        self.actions = actions
        return self
    
    def generate_or_pick_one(self, actions: List[Type[BaseModel]]):
        self.tool_choice = "auto"
        self.parallel_tool_calls = False
        self.actions = actions
        return self
    
    def generate_or_pick_many(self, actions: List[Type[BaseModel]]):
        self.tool_choice = "auto"
        self.parallel_tool_calls = True
        self.actions = actions
        return self
        
    def generate(self):
        self.tool_choice = "none"
        self.parallel_tool_calls = False
        return self
    
    # async def run_complete(
    #     self, 
    #     **kwargs
    # ) -> AIMessage:
        
    #     llm_kwargs = self.config.get_llm_args(**kwargs)
    #     # metadata["model"] = llm_kwargs.get("model", self.model)
    #     with Tracer(
    #         is_traceable=self.is_traceable,
    #         tracer_run=self.tracer_run,
    #         run_type="llm",
    #         name=self.name,
    #         inputs={"messages": [msg.to_openai() for msg in self.messages]},
    #         # metadata=metadata,
    #     ) as llm_run:
    #         try:
    #             response = await self.client.complete(
    #                 self.messages, 
    #                 actions=self.actions,
    #                 tool_choice=self.tool_choice,
    #                 run_id=str(llm_run.id),
    #                 **llm_kwargs
    #             )
    #             llm_run.end(outputs=response.raw)
    #             return response  
    #         except Exception as e:
    #             llm_run.end(errors=str(e))
    #             raise e
    async def run_complete(
        self, 
    ) -> ResponseBlock:
        with Tracer(
            run_type="llm",
            name=self.name,
            inputs={"messages": self.messages},
            # metadata=metadata,
        ) as llm_run:
            try:
                if self._complete is None:
                    raise ValueError("complete method is not set")
                if self._parse_response is None:
                    raise ValueError("parse_response method is not set")
                if self._to_tools is None:
                    raise ValueError("to_tools method is not set")
                tools = self._to_tools(self.actions)
                response = await self._complete(
                    messages=self.messages,
                    tools=tools,
                    model=self.model,
                    tool_choice=self.tool_choice,
                    **self.config.get_llm_args()
                )
                llm_run.end(outputs=response)
                return self._parse_response(response, self.actions)
            except Exception as e:
                llm_run.end(errors=str(e))
                raise e
        
                
    
    async def smart_complete(
        self, 
        # messages: List[BaseMessage], 
        # actions: Actions=None,
        # tool_choice: ToolChoice | BaseModel | None = None,
        # tracer_run=None,
        # metadata={},
        retries=3,
        smart_retry=False,
        config: LlmConfig | None = None,
        **kwargs
    ) -> AIMessage:
        for try_num in range(retries):
            try:
                response = await self.run_complete(
                    **kwargs
                )
                return response
            except LLMToolNotFound as e:
                if try_num == retries - 1:
                    raise e
                if smart_retry:
                    self.messages.append(HumanMessage(content=f"there is no such tool:\n{str(e)}"))
            except ValidationError as e:
                if try_num == retries - 1:
                    raise e
                if smart_retry:
                    self.messages.append(HumanMessage(content=f"there is a validation error for the tool:\n{str(e)}"))
            except Exception as e:
                raise e
    
    
 

# LlmClientType = Union[openai.AsyncClient, anthropic.AsyncAnthropic, BaseLlmClient]
  


class LLM(BaseModel, Generic[LLM_CLIENT, CLIENT_PARAMS, CLIENT_RESPONSE]):
    model: str
    name: str
    
    is_traceable: bool | None = True
    # client: BaseLlmClient[LLM_CLIENT, CLIENT_RESPONSE]    
    client: LLM_CLIENT  
    
    class Config:
        arbitrary_types_allowed = True   
        
        
    # def transform(self, ctx_blocks: Context) -> List[BaseMessage]:
    #     if not isinstance(blocks, list):
    #         blocks = [blocks]
    #     messages = []
    #     for block in blocks:
    #         messages.append(HumanMessage(content=block.render()))
    #     return messages
    
    
    @abstractmethod
    def to_message(self, block: BaseBlock) -> dict:
        ...
    
    # @abstractmethod
    def to_chat(self, blocks: BlockStream) -> List[BaseBlock]:
        return blocks._blocks
    
    @abstractmethod
    def parse_response(self, response: CLIENT_RESPONSE, actions: List[Type[BaseModel]] | None) -> ResponseBlock:
        ...
        
    @abstractmethod
    def complete(self, *args: CLIENT_PARAMS.args, **kwargs: CLIENT_PARAMS.kwargs) -> CLIENT_RESPONSE:
        ...
        
    @abstractmethod
    def to_tools(self, actions: List[Type[BaseModel]]) -> List[dict] | None:
        ...
    
    def __call__(
        self, 
        blocks: BlockStream,
        retries: int = 3,
        smart_retry: bool = True,
        config: LlmConfig | None = None,
        is_traceable: bool | None = True,
    ) -> LlmExecution:  
        chat_blocks = self.to_chat(blocks)
        messages = [self.to_message(b) for b in chat_blocks]
                
        llm_execution = LlmExecution(
            ctx_blocks=blocks,
            messages=messages,
            model=self.model,
            # client=self.client,
            name=self.name,
            # config=config,
            is_traceable=is_traceable
        )
        llm_execution._complete = self.complete
        llm_execution._parse_response = self.parse_response
        llm_execution._to_tools = self.to_tools
        return llm_execution
