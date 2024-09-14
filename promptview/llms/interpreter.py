from typing import Generator, List, Type
from pydantic import BaseModel
from promptview.llms.messages import HumanMessage, AIMessage, SystemMessage
from promptview.prompt.mvc import ContentBlock, add_tabs, replace_placeholders
import json 
import textwrap

from promptview.utils.function_utils import flatten_list




class Conversation(BaseModel):
    content_blocks: list[ContentBlock]
    index: int | None = None
    actions: List[Type[BaseModel]] = []
    hints: List[ContentBlock] = []

    def pre_order_traversal(self, enumerated=False) -> Generator["ContentBlock", None, None]:
        """
        Perform pre-order traversal of the tree without recursion.
        This yields each ContentBlock and its children in pre-order.
        """
        stack = [(self, 0, 0)]  # Initialize stack with the root node (self)
        
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

                
    def post_order_traversal(self) -> Generator["ContentBlock", None, None]:
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



class LlmInterpreter:
    
    
    def render_model(self, block: ContentBlock, depth):
        model = block.content
        # depth = block.depth
        prompt = ""
        if block.numerate and block.index:
            prompt += f"{block.index + 1}. "
            
        if block.base_model == 'json':
            return add_tabs(prompt + json.dumps(model.model_dump(), indent=block.indent), depth)
        elif block.base_model == 'model_dump':
            return add_tabs(prompt + str(model.model_dump()) + "\n", depth)
        else:
            raise ValueError(f"base_model type not supported: {block.base_model}")

    def render_string(self, block: ContentBlock, depth, **kwargs):
        prompt = ''
        # depth = block.depth + 1 if block.has_wrap() else block.depth
        if block.numerate and block.index:
            prompt += f"{block.index + 1}. "    
        prompt += textwrap.dedent(block.content).strip()
        prompt = add_tabs(prompt, depth)
        return replace_placeholders(prompt, **kwargs)

    def render_dict(self, block: ContentBlock, depth):
        prompt = ''
        # depth = block.depth + 1 if block.has_wrap() else block.depth
        if block.numerate and block.index:
            prompt += f"{block.index + 1}. "
        prompt += json.dumps(block.content_blocks, indent=block.indent)
        return add_tabs(prompt, depth)

    def add_wrapper(self, content: str, block: ContentBlock, depth):
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


    def render_wrapper_starting(self, block: ContentBlock, depth):
        title = block.title if block.title is not None else ''
        if block.wrap == "xml":
            return add_tabs(f"<{title}>", depth)
        elif block.wrap == "markdown":
            return add_tabs(f"## {title}", depth)
        return add_tabs(f'{title}:', depth)

    
    def render_wrapper_ending(self, block: ContentBlock, depth):
        title = block.title if block.title is not None else ''
        if block.wrap == "xml":
            return add_tabs(f"</{title}>", depth)
        return ''


    def render_block(self, block: ContentBlock, depth=0):
        results = []
        if block.has_wrap():
            depth+=1
        if block.content_blocks:
            children_depth = depth
            if block.content is not None:
                children_depth += 1            
            results = flatten_list([self.render_block(sub_block, children_depth) for sub_block in block.content_blocks])
        
        if block.get_type() != type(None):
            if issubclass(block.get_type(), str):
                results.insert(0, self.render_string(block, depth))
            elif issubclass(block.get_type(), BaseModel):
                results.insert(0, self.render_model(block, depth))    
            else:
                raise ValueError(f"Unsupported block type: {block.get_type()}")    
        if block.has_wrap():
            depth -=1
            results.insert(0, self.render_wrapper_starting(block, depth))
            results.append(self.render_wrapper_ending(block, depth))
        return results
    
    
    def run_transform(self, content_blocks: list[ContentBlock]):
        conversation = Conversation(content_blocks=content_blocks)
        current_role = None
        for (depth, index), block in conversation.pre_order_traversal(enumerated=True):
            # print("-----------------------")
            if depth == 1:
                current_role = block.role
            block.depth = depth - 1
            block.parent_role = current_role
            if issubclass(block.get_type(), BaseModel):
                conversation.hints.append(block)
            if block.actions:
                conversation.actions.extend(block.actions)
        messages = self.transform(conversation)
        return messages, conversation.actions


    def transform(self, conversation: Conversation):
        messages = []
        for block in conversation.content_blocks: 
            results = self.render_block(block)
            content = "\n".join(results) 
            if block.role == 'user':
                messages.append(HumanMessage(content=content))
            elif block.role == 'assistant':
                messages.append(AIMessage(content=content))
            elif block.role == 'system':
                messages.append(SystemMessage(content=content))
            else:
                raise ValueError(f"Unsupported role: {block.rule}")
        return messages       