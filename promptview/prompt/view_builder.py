import inspect
from functools import wraps
from typing import (Any, Awaitable, Callable, Generic, List, Literal, Type,
                    TypedDict, TypeVar)

from promptview.llms.anthropic_llm import AnthropicLLM
from promptview.llms.llm import LLM
from promptview.llms.interpreter.messages import AIMessage, BaseMessage, HumanMessage
from promptview.llms.openai_llm import OpenAiLLM
from promptview.llms.tracing.tracer import Tracer
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.execution_context import ExecutionContext
from promptview.prompt.mvc import ViewBlock, create_view_block
from promptview.prompt.types import PromptInputs, ToolChoiceParam
from promptview.state.context import Context
from promptview.utils.function_utils import call_function
from pydantic import BaseModel, Field

T = TypeVar('T')








class ViewBlockBuilder(BaseModel):
    prompt_name: str    
    
    
    async def property_to_view(self, view, property_name: str, field_info, **kwargs: Any) -> ViewBlock | None:        
        title = property_name.title()
        if not view:
            return None
        if inspect.isfunction(view):
            view = await call_function(view, **kwargs)
            if not view:
                return None
        if not isinstance(view, ViewBlock):
            extra = field_info.json_schema_extra
            if extra is not None:
                if "title" in extra:
                    title = extra["title"]
            view = create_view_block(view, property_name, title=title, role='system', tag=property_name)
        return view
    
    
    async def get_template_views(self, template, **kwargs):
        template_views = []
        for field_name, field_info in template.__class__.model_fields.items():
            if field_name in ["llm", "model", "actions", "is_traceable", "tool_choice"]:
                continue
            view = getattr(template, field_name)
            view = await self.property_to_view(view, field_name, field_info, **kwargs)
            if view is not None:
                template_views.append(view)
        if not template_views:
            return None
        return create_view_block(
                template_views,
                view_name=self.prompt_name.lower()+"_template",
                role='system',                
            )
        
    
    
    
    async def process_render_output(self, views: Any) -> ViewBlock | List[ViewBlock]:
        if isinstance(views, str) or isinstance(views, BaseModel):
            return create_view_block(views, view_name=self.prompt_name, role='user')            
        elif isinstance(views, list):
            valid_views = []
            for view in views:
                if isinstance(view, list):
                    raise ValueError("Nested lists are not supported")
                if not isinstance(view, ViewBlock):
                    valid_views.append(create_view_block(view, view_name=self.prompt_name, role='user'))
                else:
                    valid_views.append(view)
            return valid_views
            
        elif isinstance(views, tuple):
            view_name = self.prompt_name
            return create_view_block(views, view_name=view_name, role='user')            
        return views