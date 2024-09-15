from functools import wraps
import inspect
from typing import Any, Awaitable, Callable, Generic, List, Literal, Type, TypeVar, TypedDict

from pydantic import BaseModel, Field
from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.messages import AIMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.interpreter import Conversation
from promptview.llms.llm2 import LLM
from promptview.llms.tracer import Tracer
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.state.context import Context
from promptview.utils.function_utils import call_function


T = TypeVar('T')


class Prompt(BaseModel, Generic[T]):    
    is_traceable: bool = True
    llm: LLM = Field(default_factory=OpenAiLLM)
    tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None
    actions: List[Type[BaseModel]] | None = []
    
    _render_method: Callable | None = None
    _output_parser_method: Callable | None = None
    
    _name: str | None = None
    
    def render(self):
        raise NotImplementedError("render method is not set")
    
    
    async def _render(self, context=None, **kwargs: Any) -> List[ViewBlock] | ViewBlock:
        views = await call_function(
                self.render if self._render_method is None else self._render_method, 
                context=context, 
                **kwargs
            )
        if isinstance(views, str) or isinstance(views, BaseModel):
            return create_view_block(views, view_name=self.__class__.__name__.lower(), role='user')            
        elif isinstance(views, list):
            valid_views = []
            for view in views:
                if not isinstance(view, ViewBlock):
                    valid_views.append(create_view_block(view, view_name=self.name or self.__class__.__name__, role='user'))
                else:
                    valid_views.append(view)
            return valid_views
            
        elif isinstance(views, tuple):
            return create_view_block(views, view_name=self.name or self.__class__.__name__, role='user')            
        return views
    
    
    async def property_to_view(self, property_name: str, **kwargs: Any) -> ViewBlock | None:
        view = getattr(self, property_name)
        title = property_name.title()
        if not view:
            return None
        if inspect.isfunction(view):
            view = await call_function(view, **kwargs)
            if not view:
                return None
        if not isinstance(view, ViewBlock):
            view = create_view_block(view, property_name, title=title, role='system', tag=property_name)
        return view
    
    
    async def transform(self, views: List[ViewBlock] | ViewBlock | None = None, **kwargs: Any) -> T:
        template_views = []
        for field_name, field in self.model_fields.items():
            if field_name in ["llm", "model", "actions", "is_traceable", "tool_choice"]:
                continue
            # print(field_name, field)
            view = await self.property_to_view(field_name, **kwargs)
            if view is not None:
                template_views.append(view)
        system_view = create_view_block(
                template_views,
                view_name=self.__class__.__name__.lower()+"_template",
                role='system',                
            )
        if views is not None:
            if not isinstance(views, list):
                views = [views]
            return create_view_block([system_view] + views, "root")
        return create_view_block([system_view], "root")
                
    
    async def __call__(
            self,
            views: List[ViewBlock] | ViewBlock | None = None, 
            context: Context | None = None, 
            actions: List[Type[BaseModel]] | None = None,
            tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,
            tracer_run: Tracer | None=None,
            output_messages: bool = False,
            **kwargs: Any
        ) -> T:
        with Tracer(
                is_traceable=self.is_traceable if not output_messages else False,
                tracer_run=tracer_run,
                name=self._name or self.__class__.__name__,
                run_type="prompt",
                inputs={
                    "input": kwargs,
                },
            ) as prompt_run:
            try:
                actions = actions or self.actions
                views = views or await self._render(context=context, **kwargs)
                conversation = await self.transform(views, context=context, **kwargs)        
                messages, actions_ = self.llm.transform(conversation)
                if actions is None:
                    actions = actions_
                if output_messages:
                    return messages
                
                response = await self.llm.complete(messages, actions=actions, tool_choice=tool_choice, tracer_run=prompt_run, **kwargs)        
                prompt_run.end(outputs={'output': response})
                return response
            except Exception as e:
                prompt_run.end(errors=str(e))
                raise e
            
    def set_methods(self, render_func: Callable | None = None, output_parser: Callable | None = None) -> None:
        self._render_method = render_func
        self._output_parser_method = output_parser
        
    @classmethod
    def decorator_factory(cls) -> Callable[..., Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]]:
        # Define the decorator with kwargs
        def prompt_decorator(**kwargs: cls):
            # Define the actual decorator
            def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
                # Create a prompt instance with the given kwargs
                prompt = cls[T](**kwargs)
                prompt.set_methods(func)
                
                @wraps(func)
                async def wrapper(*args, **inner_kwargs) -> T:
                    # Call the prompt instance with necessary arguments
                    return await prompt(*args, **inner_kwargs)
                
                return wrapper
            
            return decorator

        return prompt_decorator

    @classmethod
    def decorator_factory(cls):
        def prompt_decorator( 
            self=None,   
            model: str = "gpt-4o",
            llm: LLM | None = None,            
            parallel_actions: bool = True,
            is_traceable: bool = True,
            output_parser: Callable[[AIMessage], T] | None = None,
            tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,
            actions: List[Type[BaseModel]] | None = None,
            **kwargs: Any
        ):
            if llm is None:
                llm = OpenAiLLM(
                    model=model, 
                    parallel_tool_calls=parallel_actions
                )
            def decorator(func) -> Callable[..., Awaitable[T]]:
                prompt = cls[T](
                        model=model,
                        llm=llm,                        
                        tool_choice=tool_choice,
                        actions=actions,
                        is_traceable=is_traceable,
                        **kwargs
                    )
                prompt._name=func.__name__
                prompt.set_methods(func, output_parser)
                # if self:
                    # self.router_prompt = prompt
                @wraps(func)
                async def wrapper(**kwargs) -> T:            
                    return await prompt(**kwargs)
                
                # wrapper.__signature__ = sig
                return wrapper
            
            return decorator
        return prompt_decorator
