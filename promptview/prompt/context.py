import contextvars
from typing import Any, List, Union
from ..conversation.models import Message
from ..llms.messages import ActionCall
from .block import ActionBlock, BaseBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from pydantic import BaseModel
from ..conversation.history import History
from collections import defaultdict
import datetime as dt

from typing import TypedDict, List
from .local_state import TurnHooks

class MessageView(TypedDict):
    content: List[str]
    role: str









class BlockStream:
    
    def __init__(
        self, 
        history: History, 
        blocks: List[BaseBlock] | None = None, 
        run_id: str | None = None, 
        prompt_name: str | None = None
    ):
        self.history = history
        self._blocks = []
        self._block_lookup = defaultdict(list)        
        if blocks:
            for b in blocks:
                self.append(b)        
        self._dirty = True
        self.response = None
        self.run_id = run_id
        self.prompt_name = prompt_name
    
    
    def __add__(self, other: Union[list[BaseBlock] , "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, BaseBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.history, self._blocks + other, run_id=self.run_id, prompt_name=self.prompt_name)
        elif isinstance(other, BlockStream):
            return BlockStream(self.history, self._blocks + other._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        else:       
            raise ValueError(f"Invalid type: {type(other)}")
        
    def __radd__(self, other: Union[list[BaseBlock], "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, BaseBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.history, other + self._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        elif isinstance(other, BlockStream):
            return BlockStream(self.history, other._blocks + self._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        else:       
            raise ValueError(f"Invalid type: {type(other)}")        
    
        
    def _update_lookup(self, block: BaseBlock):
        if isinstance(block, BaseBlock):
            if block.id:
                self._block_lookup[block.id].append(block)
            for b in block._items:
                self._update_lookup(b)            
    

    def append(self, block):
        self._blocks.append(block)
        # self._block_lookup[block.id].append(block)
        self._update_lookup(block)
    def prepend(self, block):
        self._blocks.insert(0, block)
        # self._block_lookup[block.id].insert(0, block)
        self._update_lookup(block)
        
    def insert(self, index: int, block):
        self._blocks.insert(index, block)
        # self._block_lookup[block.id].insert(index, block)
        self._update_lookup(block)
        
    def get(self, key: str | MessageView | list[str | MessageView] ):
        _key: list[str | MessageView]
        if type(key) == str or type(key) == MessageView:
            _key = [key]
        elif type(key) == list:
            _key = key
        else:
            raise ValueError(f"Invalid key type: {type(key)}")
        chat_blocks = []
        for k in _key:            
            if type(k) == str:
                if k not in self._block_lookup:
                    continue
                    # raise ValueError(f"Block with id {k} not found")
                target = self._block_lookup[k]
                chat_blocks.extend(target)
            elif type(k) == dict:                                
                chat_blocks.append(
                    TitleBlock(
                        content=self.get(k["content"]),
                        role=k.get("role", "user")
                    )
                )
                
        return chat_blocks
        
        
    def block(self, title=None, ttype: TitleType="md", role: BlockRole = "user", name: str | None = None, id: str | None = None):
        lb = TitleBlock(title=title, ttype=ttype, id=id, role=role, name=name)
        self.append(lb)
        return lb
    
    def list(self, title=None, ttype: TitleType="md", bullet: BulletType = "-", role: BlockRole = "user", name: str | None = None, id: str | None = None):        
        lb = ListBlock(title=title, ttype=ttype, bullet=bullet, id=id, role=role, name=name)
        self.append(lb)
        return lb
    
    def push(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None, id: str | None="history"):        
        if action or isinstance(block, ActionBlock):
            if isinstance(block, str) or isinstance(block, dict):
                block = ActionBlock(content=block, tool_call_id=action.id, id=id)
            elif isinstance(block, TitleBlock):
                block = ActionBlock(content=block.content, tool_call_id=action.id, id=id)
            return self.push_action(block)
        else:
            if isinstance(block, str) or isinstance(block, dict): 
                block = TitleBlock(content=block, role=role or "user", id=id)
                return self.push_message(block)
            elif isinstance(block, ResponseBlock):
                block.id = id
                return self.push_response(block)
            elif isinstance(block, TitleBlock):
                block.id = id
                return self.push_message(block)
            else:
                raise ValueError(f"Invalid block type: {type(block)}")
            
    
    def push2(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None, id: str | None="history"):        
        if isinstance(block, str) or isinstance(block, dict):
            if action:
                block = ActionBlock(content=block, tool_call_id=action.id, id=id)
                self.push_action(block)
            else:
                block = TitleBlock(content=block, role=role or "user", id=id)
                self.push_message(block)
        elif isinstance(block, ResponseBlock):
            block.id = id
            self.push_response(block)
        elif isinstance(block, ActionBlock):
            block.id = id
            self.push_action(block)
        elif isinstance(block, TitleBlock):
            block.id = id
            self.push_message(block)             
        return block
    
    def pushleft(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None):
        if isinstance(block, str) or isinstance(block, dict):
            if action:
                block = ActionBlock(content=block, tool_call_id=action.id)
                self.push_action(block, index=0)
            else:
                block = TitleBlock(content=block, role=role or "user")
                self.push_message(block, index=0)
        elif isinstance(block, ResponseBlock):
            self.push_response(block, index=0)
        elif isinstance(block, ActionBlock):
            self.push_action(block, index=0)
        elif isinstance(block, TitleBlock):
            self.push_message(block, index=0)
            

        return block
    
    
    def pushleft_system(self, block: BaseBlock):
        self.insert(0, block)

    
    # def push(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None):
    #     if isinstance(block, str) or isinstance(block, dict):
    #         if action:
    #             block = ActionBlock(content=block, tool_call_id=action.id)
    #             self.push_action(block)
    #         else:
    #             block = TitleBlock(content=block, role=role or "user")
    #             self.push_message(block)
            
    #     elif isinstance(block, ResponseBlock):
    #         self.push_response(block)
    #     elif isinstance(block, ActionBlock):
    #         self.push_action(block)
    #     return block
 

    def push_action(self, action, index: int | None = None):
        if index is None:
            self.append(action)
        else:
            self.insert(index, action)
        message = self.history.add_message(
            content=action.content,
            platform_id=action.id,
            created_at=action.created_at,
            role=action.role,
            run_id=self.run_id,
            prompt=self.prompt_name
        )
        action.message = message
        return action

    def push_response(self, response, index: int | None = None):
        # self.response = response
        if index is None:
            self.append(response)
        else:
            self.insert(index, response)
        message = self.history.add_message(
            content=response.content,
            action_calls=[a.model_dump() for a in response.action_calls],
            platform_id=response.platform_id,
            created_at=response.created_at,
            role=response.role,
            run_id=self.run_id,
            prompt=self.prompt_name
        )
        response.message = message
        return response

    def push_message(self, message, index: int | None = None):
        if index is None:
            self.append(message)
        else:
            self.insert(index, message)        
        if isinstance(message, str):
            message = self.history.add_message(
                content=message,
                role="user", 
                created_at=dt.datetime.now(),
                run_id=self.run_id,
                prompt=self.prompt_name
            )
        elif isinstance(message, BaseBlock):
            message = self.history.add_message(
                content=message.content,
                role="user", 
                created_at=message.created_at
            )
        else:
            raise ValueError(f"Invalid message type: {type(message)}")
        message.block = message
        return message
        
    def commit_turn(self):
        self.history.commit()
        
    def delete(self, block: BaseBlock):
        self.history.delete_message(id=block.db_msg_id)
        self._blocks.remove(block)
        self._block_lookup[block.id].remove(block)
        
    
    def blocks_to_messages(self, blocks: List[BaseBlock]):
        messages = []
        for block in blocks:
            if isinstance(block, ResponseBlock):
                messages.append(Message(role="assistant", content=block.render(), platform_uuid=block.platform_id, action_calls=[a.model_dump() for a in block.action_calls]))
            elif block.role == "tool":
                messages.append(Message(role="tool", content=block.render(), platform_uuid=block.platform_id))
            else:
                messages.append(Message(role="user", content=block.render(), platform_uuid=block.platform_id))
        return messages
    
    
    def __getitem__(self, key):
        return self._blocks[key]
    
    def __len__(self):
        return len(self._blocks)
    
    def display(self):
        from promptview.prompt.util.block_visualization import display_block_stream
        display_block_stream(self)




CURR_CONTEXT = contextvars.ContextVar("curr_context")



class Context:
    
    def __init__(
        self, 
        inputs: dict | None = None, 
        branch_id: int | None = None, 
        history: History | None = None,
        prompt_name: str = "global",
        run_id: str | None = None,    
    ):
        self.history = history or History()
        self.branch_id = branch_id
        self._initialized = False
        self.inputs = inputs or {}
        self._ctx_token = None
        self._hooks = None
        self.tracer = None
        self._parent_ctx = None
        self.prompt_name = prompt_name
        self.run_id = run_id
        
        
    def build_child(self, prompt_name: str):
        ctx = Context(
            inputs=self.inputs, 
            branch_id=self.branch_id, 
            history=self.history,
            prompt_name=prompt_name,
            run_id=self.run_id
        )
        ctx._parent_ctx = self        
        ctx._initialized = self._initialized
        ctx._hooks = TurnHooks(self.history, prompt_name=prompt_name)
        return ctx
    
    # def copy(self):
    #     ctx = Context(
    #         inputs=self.inputs, 
    #         branch_id=self.branch_id, 
    #         history=self.history,
    #         hooks=self._hooks,
    #         prompt_name=self.prompt_name,
    #         run_id=self.run_id
    #     )
    #     return ctx

    @staticmethod
    def get_current():
        return CURR_CONTEXT.get()    
    
    
    @property
    def session_id(self):
        return self.history.session.id
    
        
    def resume(self, new_turn: bool = True):        
        # self.init()
        self.history.init_last_session()
        if self.branch_id:
            self.history.switch_to(self.branch_id)
        self._initialized = True
        if new_turn:
            self.history.add_turn()
        self._hooks = TurnHooks(self.history, prompt_name=self.prompt_name)
        return self
    
    def start(self):
        self.history.init_new_session()
        # if self.branch_id:
        #     self.history.switch_to(self.branch_id)
        self._initialized = True
        self._hooks = TurnHooks(self.history, prompt_name=self.prompt_name)
        return self
    
    @property
    def turn(self):
        return self.history.turn
    
    @property
    def branch(self):
        return self.history.branch
    
    @property
    def session(self):
        return self.history.session
    
    @property
    def is_initialized(self):
        return self._initialized
    
    def init(self):
        self.history.init_last_session()
        if self.branch_id:
            self.history.switch_to(self.branch_id)
        self._initialized = True
        
        
    async def __aenter__(self):
        if not self._initialized:
            raise ValueError("Context not initialized. Call start() or resume() first.") 
        self._ctx_token = CURR_CONTEXT.set(self)
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self.history.commit()
        if self._ctx_token:
            CURR_CONTEXT.reset(self._ctx_token)
            self._ctx_token = None
            
    def use_state(self, key: str, initial_value: Any = None):
        if not self._hooks:
            raise ValueError("Turn hooks not initialized. Call resume() or start() first.")
        return self._hooks.use_state(key, initial_value)
            
    def messages_to_blocks(self, messages: List[Message]):
        # block_stream = BlockStream(self.history)
        blocks = []
        for message in messages:
            if message.role == "assistant":
                blocks.append(
                    ResponseBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        action_calls=message.action_calls ,
                        id="history",
                        # name=message.name, 
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
            elif message.role == "tool":
                blocks.append(
                    ActionBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        # tool_call_id=message.platform_uuid, 
                        id="history",
                        # name=message.name, 
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
            else:
                blocks.append(
                    TitleBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        role=message.role, 
                        # name=message.name, 
                        id="history",
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
        
        return blocks
        
        
    def last(self, limit=10):
        messages = self.history.get_last_messages(limit)
        blocks = self.messages_to_blocks(messages)
        block_stream = BlockStream(self.history, blocks)
        return block_stream
    
    
    def last_messages(self, limit=10):
        return self.history.get_last_messages(limit)
    
    
    def clear_session(self):
        self.history.clear_session()
    