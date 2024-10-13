from __future__ import annotations

from functools import wraps
from uuid import uuid4
from typing import (Any, Callable, Coroutine, Generator, Iterable, List,
                    Literal, ParamSpec, Sequence, Tuple, Type, Union)

from promptview.llms.interpreter.messages import (ActionCall, ActionMessage, AIMessage,
                                      BaseMessage)
from promptview.llms.utils.action_manager import Actions
from pydantic import BaseModel, Field

ViewWrapperType = Literal["xml", "markdown", None]
BaseModelRenderType =  Literal['model_dump', 'json']
ListModelRender = Literal['list', 'view_node']



RoleType = Literal["assistant", "user", "system", "tool"]
BulletType = Literal["number" , "astrix" , "dash" , "none", None] | str
StripType = Literal["left", "right"] | bool | None

def filter_by_tag(block: ViewBlock, tag: str | None) -> bool:
    return tag is None or block.tag == tag

def filter_by_role(block: ViewBlock, role: str | None) -> bool:
    return role is None or block.role == role

def filter_by_view_name(block: ViewBlock, view_name: str | None) -> bool:
    return view_name is None or block.view_name == view_name

def filter_by_class(block: ViewBlock, class_: str | None) -> bool:
    return class_ is None or block.class_ == class_

def filter_by_depth(depth: int, min_depth: int, max_depth: int) -> Callable[[ViewBlock, int], bool]:
    def inner(block: ViewBlock, current_depth: int) -> bool:
        if depth is not None:
            return current_depth == depth
        return min_depth <= current_depth <= max_depth
    return inner

def fitler_by_action_calls(block: ViewBlock, action_calls: bool | None) -> bool:
    return action_calls is None or bool(block.action_calls) == action_calls


def filter_by_ids(block: ViewBlock, uuids: list[str] | None) -> bool:
    return uuids is None or block.uuid in uuids

def combine_filters(
    tag: str | None = None, 
    role: str | None = None,
    view_name: str | None = None,
    class_: str | None = None,
    depth: int | None = None,
    min_depth: int = 0,
    max_depth: int = 100,
    action_calls: bool | None=None,
    uuids: list[str] | None = None
) -> Callable[[ViewBlock, int], bool]:
    
    def combined(block: ViewBlock, current_depth: int) -> bool:
        return (
            filter_by_tag(block, tag) and
            filter_by_role(block, role) and
            filter_by_view_name(block, view_name) and
            filter_by_class(block, class_) and
            filter_by_depth(depth, min_depth, max_depth)(block, current_depth) and 
            fitler_by_action_calls(block, action_calls) and 
            filter_by_ids(block, uuids)
        )
    
    return combined


def is_view_block_list_valid(view: list[ViewBlock]):
    for v in view:
        if not isinstance(v, ViewBlock):
            raise ValueError(f"view block list must contain only ViewBlock instances. Found: {type(v)}")
    return True
    

class ViewBlock(BaseModel):
    uuid: str = Field(default_factory=lambda: str(uuid4()), description="id of the view node")
    name: str | None = Field(None, description="name of the person who created the view")
    view_name: str
    title: str | None = None
    content: str | BaseModel | dict | None = None
    view_blocks: list[ViewBlock] = Field(default_factory=list, description="list of view blocks that are children of this view block")
    role: RoleType | None = None
    actions: list[Type[BaseModel]] | None = None
    
    tag: str | None = None
    class_: str | None = None
    parent_role: RoleType | None = None
    
    bullet: BulletType = "none"
    strip: StripType = Field(default=None, description="if the content should be stripped")
    base_model: BaseModelRenderType = 'json'
    base_model_indent: int = 2
    wrap: ViewWrapperType = None    
    role_name: str | None = None    
    index: int | None = None
    
    depth: int = 0
    indent: int = 0
    list_model: ListModelRender = 'view_node'
    action_calls: List[ActionCall] | None = None
    
    visited: bool = False
    
    def get_type(self):
        return type(self.content)
        return type(self.view_blocks)
    
    def has_wrap(self):
        return self.wrap is not None or self.title is not None
    
    def is_leaf(self):
        return self.get_type() == str or issubclass(self.get_type(), BaseModel)
    
    def __hash__(self):
        return self.uuid.__hash__()
    
    def __bool__(self):
        return bool(self.view_blocks)
    
    @property
    def action_call_uuids(self):
        if self.action_calls is None:
            return []
        return [a.id for a in self.action_calls]
    
    def find_actions(self) -> Actions:
        actions = Actions()
        for block in self.pre_order_traversal():            
            if block.actions:
                actions.extend(block.actions)
        return actions
    
    def push(self, block: ViewBlock):
        assert isinstance(block, ViewBlock)
        self.view_blocks.append(block)
        
    def extend(self, blocks: list[ViewBlock]):
        assert all(isinstance(b, ViewBlock) for b in blocks)
        self.view_blocks.extend(blocks)
    
    def add(self, blocks: list[ViewBlock] | ViewBlock):
        if isinstance(blocks, list):
            if is_view_block_list_valid(blocks):            
                self.extend(blocks)
        elif isinstance(blocks, ViewBlock):
            self.push(blocks)
        else:
            raise ValueError(f"invalid type: {type(blocks)}")
        
    def find(
        self,
        tag: str | None=None, 
        role: str | None=None, 
        view_name: str | None=None, 
        class_: str | None=None, 
        depth: int | None = None,
        min_depth: int=0, 
        max_depth: int=100,
        action_calls: bool | None=None,
        replace: bool=True,
        uuids: list[str] | None = None,
        enumerated: bool=False
        
    ) -> Generator[ViewBlock, None, None]:
                
        filter_func = combine_filters(tag, role, view_name, class_, depth, min_depth, max_depth, action_calls, uuids)
        for (current_depth, index), block in self.pre_order_traversal(enumerated=True):
            if filter_func(block, current_depth):
                if block.visited == False:
                    if not replace:
                        block.visited = True
                    if enumerated:
                        yield (current_depth, index), block
                    else:
                        yield block

            
    def first(
        self,        
        tag: str | None=None, 
        role: str | None=None, 
        view_name: str | None=None, 
        class_: str | None=None,
        depth: int | None = None,
        min_depth: int=0, 
        max_depth: int=100,
        action_calls: bool | None=None,
        uuids: list[str] | None = None,
        skip: int=0,
        enumerated: bool=False
    ) -> ViewBlock | Tuple[Tuple[int, int], ViewBlock] | None:
        """return the first block that matches the filter"""
        for (depth, index), block in self.find(
            tag, 
            role, 
            view_name, 
            class_, 
            depth, 
            min_depth, 
            max_depth, 
            action_calls=action_calls, 
            uuids=uuids,
            enumerated=True
        ):
            if skip == 0:
                if enumerated:
                    return (depth, index), block
                return block
            skip -= 1
    
    def count(
        self, 
        tag: str | None=None, 
        role: str | None=None, 
        view_name: str | None=None, 
        class_: str | None=None,
        depth: int | None = None,
        min_depth: int=0, 
        max_depth: int=100,
        action_calls: bool | None=None,
        uuids: list[str] | None = None
    ):
        """counting the number of blocks that match the filter under the current block"""
        count = 0
        for block in self.find(
            tag=tag,
            role=role,
            view_name=view_name,
            class_=class_,
            depth=depth,
            min_depth=min_depth,
            max_depth=max_depth,
            action_calls=action_calls,
            uuids=uuids
        ):
            count += 1
        return count
    
        
    def pre_order_traversal(self, enumerated=False) -> Generator[Tuple[Tuple[int, int], ViewBlock] | ViewBlock, None, None]:
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
            for i, child in enumerate(reversed(current_block.view_blocks)):
                stack.append((child, depth + 1, len(current_block.view_blocks) - 1 - i))

                
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
            if current_block.view_blocks:
                stack1.extend(current_block.view_blocks)
        
        # Second step: Pop from stack2 and yield, which ensures post-order traversal
        while stack2:
            item = stack2.pop()
            # if item is not self:
            yield item

    def replace_all(self):
        for block in self.post_order_traversal():
            block.visited = False


def transform_list_to_view_blocks(        
        items: Iterable[ViewBlock | BaseModel | str],
        view_name: str,
        role: Literal["assistant", "user", "system"] | None = None,
        bullet: Literal["number" , "astrix" , "dash" , "none", None] | str = None,
        base_model: BaseModelRenderType = 'json',
        base_model_indent: int = 2,
        indent: int = 0,
    ):
    """
    ensure that all items in the list are converted to ContentBlock
    """
    sub_views = []
    for i, o in enumerate(items):
        if isinstance(o, str):
            sub_views.append(
                ViewBlock(
                    name=None,
                    view_name=f"{view_name}_str_{i}",
                    content=o,
                    bullet=bullet,
                    index=i,
                    role=role,
                    indent=indent,
                    base_model_indent=base_model_indent,
                )   
            )
        elif isinstance(o, tuple):
            sub_views.extend(transform_list_to_view_blocks(o, view_name, role, bullet, base_model, base_model_indent, indent))
        elif isinstance(o, dict):
            # raise ValueError("dict type not supported")
            sub_views.append(
                ViewBlock(
                    name=None,
                    view_name=f"{view_name}_model_{i}",
                    content=o,
                    bullet=bullet,
                    base_model=base_model,
                    index=i,
                    role=role,
                    indent=indent
                )
            )
        elif isinstance(o, ViewBlock):
            sub_views.append(o)
        elif isinstance(o, BaseModel):
            # raise ValueError("dict type not supported")
            sub_views.append(
                ViewBlock(
                    name=None,
                    view_name=f"{view_name}_model_{i}",
                    content=o,
                    bullet=bullet,
                    base_model=base_model,
                    index=i,
                    role=role,
                    indent=indent
                )
            )
        else:
            raise ValueError(f"view type not supported: {type(o)} for view '{view_name}'")
    return sub_views




RenderViewTypes =  ViewBlock | BaseModel | str | list[str]
RenderContainerType = Sequence[RenderViewTypes] | Sequence[Sequence[RenderViewTypes]]
RenderMethodOutput = Coroutine[Any, Any, RenderContainerType] | RenderContainerType | RenderViewTypes


def create_view_block(
    views,
    view_name: str,
    name: str | None=None,
    title: str | None = None,
    wrap: ViewWrapperType = None,
    actions: List[Type[BaseModel]] | None = None,
    role: Literal["assistant", "user", "system"] = "user",
    bullet: Literal["number" , "astrix" , "dash" , "none", None] | str = None,
    strip: StripType = None,
    base_model: BaseModelRenderType = 'json',
    base_model_indent: int = 2,
    indent: int = 0,
    tag: str | None = None,
    class_: str | None = None,
):
    view_id = str(uuid4())
    content = None
    view_blocks = []
    action_calls = None
    if type(views) == list or type(views) == tuple:
        view_blocks = transform_list_to_view_blocks(
            items=views,
            view_name=view_name,
            role=role,
            bullet=bullet,
            base_model=base_model ,
            base_model_indent=base_model_indent,
            # indent=indent,
        )
    elif isinstance(views, str):
        content = views
    elif isinstance(views, dict):
        content = views
    elif isinstance(views, ViewBlock):
        # if view_name != "root":
            # raise ValueError("ViewBlock type not supported. pass a list of ContentBlock or a 'root' view_name")
        view_blocks = [views]
    elif isinstance(views, BaseMessage):
        content = views.content
        role = views.role # type: ignore
        view_id = views.id if views.id is not None else view_id
        if isinstance(views, AIMessage):
            action_calls = views.action_calls
        elif isinstance(views, ActionMessage):
            if not view_id.startswith("tool"):
                print("tool message id not starts with tool")
            print(views)
    elif isinstance(views, BaseModel):
        content = views
    return ViewBlock(
        uuid=view_id,
        view_name=view_name,
        name=name,
        title=title,
        view_blocks=view_blocks,
        content=content,
        actions=actions,
        base_model=base_model,
        base_model_indent=base_model_indent,
        bullet=bullet,
        strip=strip,
        wrap=wrap,
        role=role,
        indent=indent,
        tag=tag,
        class_=class_,
        action_calls=action_calls
    )

P = ParamSpec("P")
    
def view(
    container=None, 
    title: str | None=None,
    actions: List[Type[BaseModel]] | None=None, 
    role: Literal["assistant", "user", "system"]="user",
    name: str | None=None,
    bullet: Literal["number" , "astrix" , "dash" , "none", None] | str=None,
    strip: StripType = None,
    base_model: BaseModelRenderType = 'json',
    base_model_indent: int = 2,
    wrap: ViewWrapperType = None,
    indent: int = 0,
    class_: str | None = None,
    tag: str | None = None,
    ):

    def decorator(func: Callable[P, RenderViewTypes]):
        @wraps(func)
        def wrapper(*args, **kwargs) -> ViewBlock:
            outputs = func(*args, **kwargs)
            if container is not None:
                outputs = container(*outputs if isinstance(outputs, tuple) else (outputs,))
            block_instance = create_view_block(
                views=outputs,
                view_name=func.__name__, 
                name=name, 
                title=title, 
                wrap=wrap, 
                actions=actions, 
                role=role, 
                bullet=bullet,
                strip=strip, 
                base_model=base_model,
                base_model_indent=base_model_indent,
                indent=indent, 
                tag=tag,
                class_=class_
            )               
            return block_instance            
        return wrapper    
    return decorator

def list_view(rules: list[str], numbered: bool = True):
    if numbered:
        return "\n".join([f"{i}. {r}" for i, r in enumerate(rules)])
    else:
        return "\n".join(rules)


