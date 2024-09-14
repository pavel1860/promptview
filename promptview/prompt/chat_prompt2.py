import inspect
from typing import Any, Callable, Generic, List, Literal, Type, TypeVar

from pydantic import BaseModel, Field
from promptview.llms.anthropic_llm import AnthtropicLLM
from promptview.llms.interpreter import Conversation
from promptview.llms.llm2 import LLM
from promptview.llms.tracer import Tracer
from promptview.prompt.mvc import ContentBlock, create_content_block
from promptview.state.context import Context
from promptview.utils.function_utils import call_function


T = TypeVar('T')


class Prompt(BaseModel, Generic[T]):    
    # model: str= "gpt-3.5-turbo-0125"
    llm: LLM = Field(default_factory=AnthtropicLLM)
    actions: List[Type[BaseModel]] | None = []
    
    _render_method: Callable | None = None
    
    def render(self):
        raise NotImplementedError("render method is not set")
    
    
    async def _render(self, context=None, **kwargs: Any) -> List[ContentBlock] | ContentBlock:
        views = await call_function(
                self.render if self._render_method is None else self._render_method, 
                context=context, 
                **kwargs
            )
        if isinstance(views, str) or isinstance(views, BaseModel):
            return create_content_block(views, view_name=self.__class__.__name__.lower(), role='user')            
        elif isinstance(views, list):
            valid_views = []
            for view in views:
                if not isinstance(view, ContentBlock):
                    valid_views.append(create_content_block(view, view_name=self.name or self.__class__.__name__, role='user'))
                else:
                    valid_views.append(view)
            return valid_views
            
        elif isinstance(views, tuple):
            return create_content_block(views, view_name=self.name or self.__class__.__name__, role='user')            
        return views
    
    
    async def property_to_view(self, property_name: str, **kwargs: Any) -> ContentBlock | None:
        view = getattr(self, property_name)
        title = property_name.title()
        if not view:
            return None
        if inspect.isfunction(view):
            view = await call_function(view, **kwargs)
            if not view:
                return None
        if not isinstance(view, ContentBlock):
            view = create_content_block(view, property_name, title=title, role='system', tag=property_name)
        return view
    
    
    async def transform(self, views: List[ContentBlock] | ContentBlock | None = None, **kwargs: Any) -> T:
        template_views = []
        for field_name, field in self.model_fields.items():
            if field_name in ["llm", "model", "actions"]:
                continue
            # print(field_name, field)
            view = await self.property_to_view(field_name, **kwargs)
            if view is not None:
                template_views.append(view)
        system_view = create_content_block(
                template_views,
                view_name=self.__class__.__name__.lower()+"_template",
                role='system',                
            )
        if views is not None:
            if not isinstance(views, list):
                views = [views]
            return Conversation([system_view] + views)
        return Conversation([system_view])
                
    
    async def __call__(
            self,
            views: List[ContentBlock] | ContentBlock | None = None, 
            context: Context | None = None, 
            actions: List[Type[BaseModel]] | None = None,
            tool_choice: Literal['auto', 'required', 'none'] | BaseModel | None = None,
            tracer_run: Tracer | None=None,
            output_messages: bool = False,
            **kwargs: Any
        ) -> T:
        actions = actions or self.actions
        views = views or await self._render(context=context, **kwargs)
        conversation = await self.transform(views, context=context, **kwargs)
        messages = self.llm.transform(conversation)
        if output_messages:
            return messages
        
        if conversation.actions:            
            actions = actions + conversation.actions if actions else conversation.actions
        response = await self.llm.complete(messages, actions=actions, tool_choice=tool_choice, tracer_run=tracer_run, **kwargs)        
        return response