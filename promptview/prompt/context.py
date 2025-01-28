import contextvars
from typing import List, Union
from promptview.conversation.models import Message
from promptview.llms.messages import ActionCall
from promptview.prompt.block import ActionBlock, BaseBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from pydantic import BaseModel
from promptview.conversation.history import History
from collections import defaultdict
import datetime as dt

from typing import TypedDict, List

class MessageView(TypedDict):
    content: List[str]
    role: str









class BlockStream:
    
    def __init__(self, history: History, blocks: List[BaseBlock] | None = None):
        self.history = history
        self._blocks = []
        self._block_lookup = defaultdict(list)        
        if blocks:
            for b in blocks:
                self.append(b)        
        self._dirty = True
        self.response = None
    
    
    def __add__(self, other: Union[list[BaseBlock] , "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, BaseBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.history, self._blocks + other)
        elif isinstance(other, BlockStream):
            return BlockStream(self.history, self._blocks + other._blocks)
        else:       
            raise ValueError(f"Invalid type: {type(other)}")
        
    def __radd__(self, other: Union[list[BaseBlock], "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, BaseBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.history, other + self._blocks)
        elif isinstance(other, BlockStream):
            return BlockStream(self.history, other._blocks + self._blocks)
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
            role="tool",
            platform_id=action.id,
            created_at=action.created_at
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
            role="assistant",
            action_calls=[a.model_dump() for a in response.action_calls],
            platform_id=response.platform_id,
            created_at=response.created_at
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
                created_at=dt.datetime.now()
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
    
    def __init__(self, inputs: dict | None = None, branch_id: int | None = None):
        self.history = History()
        self.branch_id = branch_id
        self._initialized = False
        self.inputs = inputs or {}
        self._ctx_token = None
        

    # @staticmethod
    # def resume(branch_id: int | None = None):
    #     ctx = Context(branch_id=branch_id)
    #     ctx.init()
    #     ctx.history.add_turn()
    #     return ctx
    
    # @staticmethod
    # def start():
    #     ctx = Context()
    #     ctx.history.init_new_session()   
    #     ctx._initialized = True
    #     return ctx
    @classmethod
    def get_current(cls):
        return CURR_CONTEXT.get()
        
    def resume(self):        
        # self.init()
        self.history.init_last_session()
        if self.branch_id:
            self.history.switch_to(self.branch_id)
        self._initialized = True
        self.history.add_turn()
        return self
    
    def start(self):
        self.history.init_new_session()
        # if self.branch_id:
        #     self.history.switch_to(self.branch_id)
        self._initialized = True
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
    