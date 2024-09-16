import json
import textwrap
from typing import Generator, List, Tuple, Type, Union

from promptview.llms.messages import (AIMessage, BaseMessage, HumanMessage,
                                      SystemMessage)
from promptview.llms.utils.action_manager import Actions
from promptview.prompt.mvc import (BulletType, StripType, ViewBlock, add_tabs,
                                   replace_placeholders)
from promptview.utils.function_utils import flatten_list
from pydantic import BaseModel


class Conversation:
    content_blocks: list[ViewBlock]
    index: int | None = None
    actions: Actions = []
    hints: List[ViewBlock] = []
    
    
    def __init__(self, content_blocks: list[ViewBlock]):
        self.content_blocks=content_blocks
        current_role = None
        for (depth, index), block in self.pre_order_traversal(enumerated=True):
            # print("-----------------------")
            if depth == 1:
                current_role = block.role
            block.depth = depth - 1
            block.parent_role = current_role
            if issubclass(block.get_type(), BaseModel):
                self.hints.append(block)
            if block.actions:
                self.actions.extend(block.actions)
                
    
    def find_actions(self) -> Actions:
        actions = Actions()
        for block in self.pre_order_traversal():            
            if block.actions:
                actions.extend(block.actions)
        return actions
        
        
    def find(
        self,
        tag: str=None, 
        role: str=None, 
        view_name: str=None, 
        class_: str=None, 
        min_depth: int=0, 
        max_depth: int=100,
        replace: bool=True,
        node=None,
        
    ) -> Generator[ViewBlock, None, None]:
        for block in self.pre_order_traversal(node):
            # print(block.class_)
            # print(block.tag)
            if tag and block.tag != tag:
                continue
            if role and block.role != role:
                continue
            if class_ and block.class_ != class_:
                continue
            if view_name and block.view_name != view_name:
                continue
            if block.depth < min_depth or block.depth > max_depth:
                continue
            
            if not replace:
                block.visited = True            
            yield block
            
    def first(
        self,        
        tag: str=None, 
        role: str=None, 
        view_name: str=None, 
        class_: str=None, 
        min_depth: int=0, 
        max_depth: int=100,
        node=None,
        skip: int=0
    ) -> ViewBlock:
        
        for block in self.find(tag, role, view_name, class_, min_depth, max_depth, node=node):
            if skip == 0:
                return block
            skip -= 1
    
    
        
    def pre_order_traversal(self, node=None, enumerated=False) -> Generator[ViewBlock, None, None]:
        """
        Perform pre-order traversal of the tree without recursion.
        This yields each ContentBlock and its children in pre-order.
        """
        node = node or self
        stack = [(node, 0, 0)]  # Initialize stack with the root node (self)
        
        while stack:
            current_block, depth, child_index = stack.pop()
            if current_block is not self:
                if enumerated:
                    yield (depth, child_index), current_block
                else:
                    yield current_block
            
            # Add children to the stack in reverse order so they are processed in the correct order
            for i, child in enumerate(reversed(current_block.content_blocks)):
                stack.append((child, depth + 1, len(current_block.content_blocks) - 1 - i))
                
    def count(
        self, 
        tag: str=None, 
        role: str=None, 
        view_name: str=None, 
        class_: str=None, 
        min_depth: int=0, 
        max_depth: int=100,
        node=None):
        count = 0
        for block in self.find(
            tag=tag,
            role=role,
            view_name=view_name,
            class_=class_,
            min_depth=min_depth,
            max_depth=max_depth,
            node=node
        ):
            count += 1
        return count

                
    def post_order_traversal(self) -> Generator[ViewBlock, None, None]:
        """
        Perform post-order traversal of the tree without recursion.
        This yields each ContentBlock and its children in post-order.
        """
        stack1 = [self]  # Stack to store the nodes for traversal
        stack2 = []  # Stack to reverse the order of processing
        
        # First step: Visit nodes and push them onto stack2 in reverse order
        while stack1:
            current_block = stack1.pop()
            stack2.append(current_block)
            
            # Add children to stack1 (normal order, they'll be reversed in stack2)
            if current_block.content_blocks:
                stack1.extend(current_block.content_blocks)
        
        # Second step: Pop from stack2 and yield, which ensures post-order traversal
        while stack2:
            item = stack2.pop()
            if item is not self:
                yield item

    def replace_all(self):
        for block in self.post_order_traversal():
            block.visited = False

class LlmInterpreter:
    
    
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
        return replace_placeholders(prompt, **kwargs)
    

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


    def render_wrapper_starting(self, block: ViewBlock, depth):
        title = block.title if block.title is not None else ''
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
    
    
    # def run_transform(self, content_blocks: list[ViewBlock]):
    #     conversation = Conversation(content_blocks=content_blocks)
    #     current_role = None
    #     for (depth, index), block in conversation.pre_order_traversal(enumerated=True):
    #         # print("-----------------------")
    #         if depth == 1:
    #             current_role = block.role
    #         block.depth = depth - 1
    #         block.parent_role = current_role
    #         if issubclass(block.get_type(), BaseModel):
    #             conversation.hints.append(block)
    #         if block.actions:
    #             conversation.actions.extend(block.actions)
    #     messages = self.transform(conversation)
    #     return messages, conversation.actions


    def transform(self, root_block: ViewBlock, **kwargs) -> Tuple[List[BaseMessage], Actions]:
        messages = []
        for block in root_block.find(depth=1): 
            content = self.render_block(block, **kwargs)
            # content = "\n".join(results) 
            if block.role == 'user':
                messages.append(HumanMessage(content=content))
            elif block.role == 'assistant':
                messages.append(AIMessage(content=content))
            elif block.role == 'system':
                messages.append(SystemMessage(content=content))
            else:
                raise ValueError(f"Unsupported role: {block.role}")
        actions = root_block.find_actions()
        return messages, actions