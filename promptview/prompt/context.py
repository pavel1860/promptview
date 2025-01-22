from typing import List
from promptview.conversation.models import Message
from promptview.prompt.block import ActionBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from pydantic import BaseModel
from promptview.conversation.history import History
from collections import defaultdict


from typing import TypedDict, List

class MessageView(TypedDict):
    content: List[str]
    role: str



class CtxBlocks:
    
    def __init__(self, input: str | None = None):
        self.history = History()
        self._blocks = []
        self._dirty = True
        self.response = None
        self.input = input
        self._block_lookup = defaultdict(list)
        
    def init(self):
        self.history.init_main()

    def append(self, block):
        self._blocks.append(block)
        self._block_lookup[block.id].append(block)
        
    def get_blocks(self, key: str | MessageView | list[str | MessageView] ):
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
                    raise ValueError(f"Block with id {k} not found")
                target = self._block_lookup[k]
                chat_blocks.extend(target)
            elif type(k) == dict:                                
                chat_blocks.append(
                    TitleBlock(
                        content=self.get_blocks(k["content"]),
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
    
    def push(self, block, action: BaseModel | None = None):
        self.append(block)
        if action:
            self.append(action)

    def push_action(self, action):
        self.append(action)

    def push_response(self, response):
        self.response = response
        self.append(response)

    def push_message(self, message):
        self.append(message)
        
    def messages_to_blocks(self, messages: List[Message]):
        for message in messages:
            if message.role == "assistant":
                self.append(
                    ResponseBlock(
                        content=message.content, 
                        action_calls=message.action_calls ,
                        id="history",
                        # name=message.name, 
                        platform_uuid=message.platform_uuid
                    ))
            elif message.role == "tool":
                self.append(
                    ActionBlock(
                        content=message.content, 
                        # tool_call_id=message.platform_uuid, 
                        id="history",
                        # name=message.name, 
                        platform_uuid=message.platform_uuid
                    ))
            else:
                self.append(TitleBlock(
                    content=message.content, 
                    role=message.role, 
                    # name=message.name, 
                    id="history",
                    platform_uuid=message.platform_uuid
                ))
        
        return self._blocks
            
        
    def last(self, limit=10):
        blocks = self.history.last(limit)
        return self.messages_to_blocks(blocks)  
    
    def __getitem__(self, key):
        # if self._dirty:
        #     self._dirty = False
        #     self._blocks = self.history.last()            
        return self._blocks[key]
    
