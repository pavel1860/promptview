
            
from typing import Any, Callable, Generic, List, ParamSpec, Type, TypeVar
from promptview.llms.llm import LLM
from promptview.llms.interpreter.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.prompt.base_prompt import Prompt
from promptview.prompt.mvc import RenderMethodOutput
from promptview.prompt.types import ToolChoiceParam
from pydantic import BaseModel, Field

T = ParamSpec("T")
R = TypeVar("R")  

class ChatPrompt(Prompt[T], Generic[T]):
    background: str | List[str] | Callable | None = Field(None, description="Background information to provide context for the prompt", json_schema_extra={"title": None})
    task: str | List[str] | Callable | None = None
    rules: str | List[str] | Callable | None = None 
    examples: str | List[str] | Callable | None = None 
    output_format: str | List[str] | Callable | None  = None


P = ParamSpec("P")
# prompt = decorator_factory(ChatPrompt)

def prompt(
    model: str = "gpt-4o",
    llm: LLM | None = None,
    parallel_actions: bool = True,
    is_traceable: bool = True,
    output_parser: Callable[[AIMessage], R] | None = None,
    tool_choice: ToolChoiceParam = None,
    actions: List[Type[BaseModel]] | None = None,
    **kwargs: Any
)-> Callable[[Callable[P, RenderMethodOutput]], Prompt[P]]:
    if llm is None:
        if model.startswith("gpt"):
            llm = OpenAiLLM(
                model=model, 
                parallel_tool_calls=parallel_actions
            )
        elif model.startswith("claude"):
            from promptview.llms.anthropic_llm import AnthropicLLM
            llm = AnthropicLLM(
                model=model, 
                parallel_tool_calls=parallel_actions
            )
    def decorator(func: Callable[P, RenderMethodOutput]) -> Prompt[P]:
        prompt = ChatPrompt(
                model=model, #type: ignore
                llm=llm,                        
                tool_choice=tool_choice or ChatPrompt.get_default_field("tool_choice"),
                actions=actions,
                is_traceable=is_traceable,
                **kwargs
            )
        prompt._name=func.__name__
        prompt.set_methods(func, output_parser)            
        return prompt        
    return decorator