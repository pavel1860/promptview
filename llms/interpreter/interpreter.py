import json
import textwrap
from typing import Generator, List, Tuple, Type, Union

from promptview.llms.interpreter.messages import (ActionMessage, AIMessage, BaseMessage,
                                      HumanMessage, SystemMessage)
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import (BulletType, StripType, ViewBlock, add_tabs,
                                   replace_placeholders)
from promptview.templates.action_template import system_action_view
from promptview.utils.function_utils import flatten_list
from promptview.utils.string_utils import SafeJinjaFormatter
from pydantic import BaseModel, Field


class LlmInterpreter(BaseModel):
    
    
    formatter: SafeJinjaFormatter = Field(default_factory=SafeJinjaFormatter)
    # def __init__(self):
        # self.formatter = SafeJinjaFormatter()
        
    class Config:
        arbitrary_types_allowed = True
    
    
    def render_model(self, block: ViewBlock, depth):
        model = block.content
        prompt = ""
        if block.bullet and block.index:
            prompt += f"{block.index + 1}. "
            
        if block.base_model == 'json':
            return add_tabs(prompt + json.dumps(model.model_dump(), indent=block.indent), depth)
        elif block.base_model == 'model_dump':
            return add_tabs(prompt + str(model.model_dump()) + "\n", depth)
        else:
            raise ValueError(f"base_model type not supported: {block.base_model}")

    def render_string(self, block: ViewBlock, depth, index, bullet: BulletType, **kwargs):
           
        if bullet is None or bullet == "none":
            prompt = ""
        elif bullet == "number":
            prompt = f"{index + 1}. "
        elif bullet == "bullet":
            prompt = "• "
        elif bullet == "dash":
            prompt = "- "
        elif bullet == "astrix":
            prompt = "* "
        else:
            if type(bullet) == str:
                prompt = f"{bullet} "
            else:
                prompt = ""
            
        prompt += textwrap.dedent(block.content).strip()
        prompt = add_tabs(prompt, depth)
        return self.formatter(prompt, **kwargs)
    

    def render_dict(self, block: ViewBlock, depth):
        prompt = ''
        if block.bullet and block.index:
            prompt += f"{block.index + 1}. "
        prompt += json.dumps(block.view_blocks, indent=block.indent)
        return add_tabs(prompt, depth)

    def add_wrapper(self, content: str, block: ViewBlock, depth):
        title = block.title if block.title is not None else ''
        if block.wrap == "xml":
            return add_tabs((
                f"<{title}>\n"
                f"\n{content}"
                f"</{title}>\n"   
            ), depth)
        
        if block.wrap == "markdown":
            return add_tabs((
                f"## {title}\n"
                f"\t{content}\n"
            ), depth)
        return add_tabs((
            f"{title}:"
            f"\t{content}"
            ), depth)


    def render_wrapper_starting(self, block: ViewBlock, depth, **kwargs):
        title = block.title if block.title is not None else ''
        # title = replace_placeholders(title, **kwargs)
        title = self.formatter(title, **kwargs)
        if block.wrap == "xml":
            return add_tabs(f"<{title}>", depth)
        elif block.wrap == "markdown":
            return add_tabs(f"## {title}", depth)
        return add_tabs(f'{title}:', depth)

    
    def render_wrapper_ending(self, block: ViewBlock, depth):
        title = block.title if block.title is not None else ''
        if block.wrap == "xml":
            return add_tabs(f"</{title}>", depth)
        return ''
    
    def strip_content(self, content: str, strip_type: StripType):
        if strip_type == True:
            return content.strip()
        elif strip_type == "left": 
            return content.lstrip()
        elif strip_type == "right":
            return content.rstrip()
        return content
        
    


    def render_block(self, block: ViewBlock, depth=0, index: int | None=None, bullet: BulletType=None, **kwargs):
        results = []
        depth += block.indent
        if block.has_wrap():
            depth+=1
        if block.view_blocks:
            children_depth = depth
            if block.content is not None:
                children_depth += 1            
            # results = flatten_list([self.render_block(sub_block, children_depth, i, block.bullet, **kwargs) for i, sub_block in enumerate(block.view_blocks)])
            results = [self.render_block(sub_block, children_depth, i, block.bullet, **kwargs) for i, sub_block in enumerate(block.view_blocks)]
        
        if block.get_type() != type(None):
            if issubclass(block.get_type(), str):
                results.insert(0, self.render_string(block, depth, index, bullet, **kwargs))
            elif issubclass(block.get_type(), BaseModel):
                results.insert(0, self.render_model(block, depth))    
            else:
                raise ValueError(f"Unsupported block type: {block.get_type()}")    
        if block.has_wrap():
            depth -=1
            results.insert(0, self.render_wrapper_starting(block, depth))
            results.append(self.render_wrapper_ending(block, depth))
        
        content = "\n".join(results)
        if block.strip:
            content = self.strip_content(content, block.strip)
        return content
    



    def transform(self, root_block: ViewBlock, actions: Actions | List[Type[BaseModel]] | None = None, **kwargs) -> Tuple[List[BaseMessage], Actions]:
        messages = []
        if not isinstance(actions, Actions):
            actions = Actions(actions=actions)
        actions.extend(root_block.find_actions())
        system_block = root_block.first(role="system", depth=1)
        if system_block and actions:
            system_block.push(system_action_view(actions))
        for block in root_block.find(depth=1): 
            content = self.render_block(block, **kwargs)
            if block.role == 'user':
                messages.append(HumanMessage(id=block.uuid, content=content))
            elif block.role == 'assistant':
                messages.append(AIMessage(id=block.uuid, content=content, action_calls=block.action_calls))
            elif block.role == 'system':
                messages.append(SystemMessage(id=block.uuid, content=content))
            elif block.role == 'tool':
                messages.append(ActionMessage(id=block.uuid, content=content))
            else:
                raise ValueError(f"Unsupported role: {block.role}")
        
        return messages, actions