from typing import List
from promptview.conversation.models import Message
from promptview.llms.messages import ActionCall
from promptview.prompt.block import ActionBlock, BaseBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from pydantic import BaseModel
from promptview.conversation.history import History
from collections import defaultdict


from typing import TypedDict, List

class MessageView(TypedDict):
    content: List[str]
    role: str









class BlockStream:
    
    def __init__(self, history: History, messages: List[Message] | None = None):
        self.history = history
        self._blocks = []
        self._block_lookup = defaultdict(list)
        if messages:
            self.messages_to_blocks(messages)                    
        self._dirty = True
        self.response = None
        

    def append(self, block):
        self._blocks.append(block)
        self._block_lookup[block.id].append(block)
        
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
    
    def push(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None):
        if isinstance(block, str) or isinstance(block, dict):
            if action:
                block = ActionBlock(content=block, tool_call_id=action.id)
                self.push_action(block)
            else:
                block = TitleBlock(content=block, role=role or "user")
                self.push_message(block)
            
        elif isinstance(block, ResponseBlock):
            self.push_response(block)
        elif isinstance(block, ActionBlock):
            self.push_action(block)
        return block
        

    def push_action(self, action):
        self.append(action)
        message = self.history.add_message(
            content=action.content,
            role="tool",
            platform_id=action.id
        )
        action.message = message
        return action

    def push_response(self, response):
        # self.response = response
        self.append(response)
        message = self.history.add_message(
            content=response.content,
            role="assistant",
            action_calls=[a.model_dump() for a in response.action_calls],
            platform_id=response.platform_id
        )
        response.message = message
        return response

    def push_message(self, message):
        self.append(message)        
        if isinstance(message, str):
            message = self.history.add_message(
                content=message,
                role="user",            
            )
        elif isinstance(message, BaseBlock):
            message = self.history.add_message(
                content=message.content,
                role="user",            
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
        
    def messages_to_blocks(self, messages: List[Message]):
        for message in messages:
            if message.role == "assistant":
                self.append(
                    ResponseBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        action_calls=message.action_calls ,
                        id="history",
                        # name=message.name, 
                        platform_id=message.platform_id
                    ))
            elif message.role == "tool":
                self.append(
                    ActionBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        # tool_call_id=message.platform_uuid, 
                        id="history",
                        # name=message.name, 
                        platform_id=message.platform_id
                    ))
            else:
                self.append(
                    TitleBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        role=message.role, 
                        # name=message.name, 
                        id="history",
                        platform_id=message.platform_id
                    ))
        
        return self._blocks
    
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
    
    # def last(self, limit=10):
    #     messages = self.history.last(limit)
    #     return self.messages_to_blocks(messages)  
    
    # def last_messages(self, limit=10):
    #     messages = self.history.last(limit)
    #     return messages
    
    
    def __getitem__(self, key):
        # if self._dirty:
        #     self._dirty = False
        #     self._blocks = self.history.last()            
        return self._blocks[key]
    






class Context:
    
    def __init__(self, branch_id: int | None = None):
        self.history = History()
        self.branch_id = branch_id        
            
    async def __aenter__(self):
        self.history.init_last_session()
        if self.branch_id:
            self.history.switch_to(self.branch_id)
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        self.history.commit()
        
        
    def last(self, limit=10):
        messages = self.history.get_last_messages(limit)
        blocks = BlockStream(self.history, messages)
        return blocks
    
    