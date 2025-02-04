import contextvars
from enum import Enum
from typing import Any, List, Union, Dict
from ..conversation.models import Message
from ..llms.interpreter.messages import ActionCall
from .block import ActionBlock, BaseBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from src.db.repositories.history import History
from prisma.models import ChatbotMessageSession, ChatbotBranch, ChatbotTurn, ChatbotMessage
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
    
    async def push(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None, id: str | None="history"):        
        if action or isinstance(block, ActionBlock):
            if isinstance(block, str) or isinstance(block, dict):
                block = ActionBlock(content=block, tool_call_id=action.id, id=id)
            elif isinstance(block, TitleBlock):
                block = ActionBlock(content=block.content, tool_call_id=action.id, id=id)
            return await self.push_action(block)
        else:
            if isinstance(block, str) or isinstance(block, dict): 
                block = TitleBlock(content=block, role=role or "user", id=id)
                return await self.push_message(block)
            elif isinstance(block, ResponseBlock):
                block.id = id
                return await self.push_response(block)
            elif isinstance(block, TitleBlock):
                block.id = id
                return await self.push_message(block)
            else:
                raise ValueError(f"Invalid block type: {type(block)}")
            
    async def push2(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None, id: str | None="history"):        
        if isinstance(block, str) or isinstance(block, dict):
            if action:
                block = ActionBlock(content=block, tool_call_id=action.id, id=id)
                await self.push_action(block)
            else:
                block = TitleBlock(content=block, role=role or "user", id=id)
                await self.push_message(block)
        elif isinstance(block, ResponseBlock):
            block.id = id
            await self.push_response(block)
        elif isinstance(block, ActionBlock):
            block.id = id
            await self.push_action(block)
        elif isinstance(block, TitleBlock):
            block.id = id
            await self.push_message(block)             
        return block
    
    async def pushleft(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None):
        if isinstance(block, str) or isinstance(block, dict):
            if action:
                block = ActionBlock(content=block, tool_call_id=action.id)
                await self.push_action(block, index=0)
            else:
                block = TitleBlock(content=block, role=role or "user")
                await self.push_message(block, index=0)
        elif isinstance(block, ResponseBlock):
            await self.push_response(block, index=0)
        elif isinstance(block, ActionBlock):
            await self.push_action(block, index=0)
        elif isinstance(block, TitleBlock):
            await self.push_message(block, index=0)
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
 

    async def push_action(self, action, index: int | None = None):
        if index is None:
            self.append(action)
        else:
            self.insert(index, action)
        message = await self.history.add_message(
            content=action.content,
            platform_id=action.id,
            created_at=action.created_at,
            role=action.role,
            # run_id=self.run_id,
            prompt=self.prompt_name
        )
        action.message = message
        return action

    async def push_response(self, response, index: int | None = None):
        if index is None:
            self.append(response)
        else:
            self.insert(index, response)
        message = await self.history.add_message(
            content=response.content,
            action_calls=[a.model_dump() for a in response.action_calls],
            platform_id=response.platform_id,
            created_at=response.created_at,
            role=response.role,
            # run_id=self.run_id,
            prompt=self.prompt_name
        )
        response.message = message
        return response

    async def push_message(self, message, index: int | None = None):
        if index is None:
            self.append(message)
        else:
            self.insert(index, message)        
        if isinstance(message, str):
            message = await self.history.add_message(
                content=message,
                role="user", 
                created_at=dt.datetime.now(),
                # run_id=self.run_id,
                prompt=self.prompt_name
            )
        elif isinstance(message, TitleBlock):
            message.message = await self.history.add_message(
                content=message.content,
                role=message.role,
                created_at=message.created_at or dt.datetime.now(),
                # run_id=self.run_id,
                prompt=self.prompt_name
            )
        return message
        
    async def commit_turn(self):
        await self.history.commit()

    async def delete(self, block: BaseBlock):
        if block.db_msg_id:
            await self.history.delete_message(id=block.db_msg_id)
        self._blocks.remove(block)
        if block.id in self._block_lookup:
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
        from src.utils.generative.prompt.block_visualization import display_block_stream
        display_block_stream(self)




CURR_CONTEXT = contextvars.ContextVar("curr_context")


class InitMethod(Enum):
    START = "start"
    RESUME = "resume"
    RESUME_SESSION = "resume_session"
class Context:
    
    def __init__(
        self, 
        inputs: dict | None = None, 
        history: History | None = None,
        prompt_name: str = "global",
        run_id: str | None = None,    
    ):
        self.history = history or History()
        self._initialized = False
        self.inputs = inputs or {}
        self._ctx_token = None
        self._hooks = None
        self.tracer = None
        self._parent_ctx = None
        self.prompt_name = prompt_name
        self.run_id = run_id
        self._init_method: Dict[str, Any] | None = None
        
        
    def build_child(self, prompt_name: str):
        ctx = Context(
            inputs=self.inputs, 
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
    
    
    def set_context(self):
        self._ctx_token = CURR_CONTEXT.set(self)
    
    def reset_context(self):
        if self._ctx_token:
            try: 
                CURR_CONTEXT.reset(self._ctx_token)
            except ValueError as e:
                print(f"Warning: failed to reset context, probably because generator was closed improperly:")
            self._ctx_token = None
    
    
    @property
    def session_id(self):
        return self.history.session.id

    
    
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
    
    async def init(self):
        if not self._initialized:
            await self.history.init_new_session()
            self._initialized = True
            
    async def cleanup(self):
        await self.history.cleanup()
        
    async def commit(self):
        await self.history.commit()
        
    async def add_turn(self):
        await self.history.add_turn()
        
    async def get_last_messages(self, limit: int = 10):
        return await self.history.get_last_messages(limit)
    
    def resume_session(self, session_id: str, branch_id: str | None = None, new_turn: bool = True):
        self._init_method = {
            "type": InitMethod.RESUME,
            "kwargs": {"session_id": session_id, "branch_id": branch_id, "new_turn": new_turn}
        }
        return self
    
    def resume(self, new_turn: bool = True):
        self._init_method = {
            "type": InitMethod.RESUME,
            "kwargs": {"new_turn": new_turn}
        }
        return self
        
    def start(self):
        self._init_method = {
            "type": InitMethod.START,
            "kwargs": {}
        }
        return self
    
    async def _resume(self, new_turn: bool = True):        
        await self.history.init_last_session()
        if self.branch_id:
            await self.history.switch_to(self.branch_id)
        self._initialized = True
        if new_turn:
            await self.history.add_turn()
        self._hooks = TurnHooks(self.history, prompt_name=self.prompt_name)
        return self
    
    async def _start(self):
        await self.history.init_new_session()
        self._initialized = True
        self._hooks = TurnHooks(self.history, prompt_name=self.prompt_name)
        return self
    
    async def _resume_session(self, session_id: str, branch_id: str | None = None, new_turn: bool = True):
        await self.history.init_session(session_id, branch_id)        
        self._initialized = True
        if new_turn:
            await self.history.add_turn()
        self._hooks = TurnHooks(self.history, prompt_name=self.prompt_name)
        return self
        
    async def __aenter__(self):
        if not self._initialized:
            if not self._init_method:
                raise ValueError("Init method not set. Call resume() or start() first.")
            if self._init_method["type"] == InitMethod.RESUME:
                await self._resume(**self._init_method["kwargs"])
            elif self._init_method["type"] == InitMethod.START:
                await self._start()
            elif self._init_method["type"] == InitMethod.RESUME_SESSION:
                await self._resume_session(**self._init_method["kwargs"])
            
        self.set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        # await self.commit()
        self.reset_context()
        
    def use_hooks(self, prompt_name: str | None = None) -> TurnHooks:
        return TurnHooks(self.history, prompt_name or self.prompt_name)
    
    async def use_state(self, key: str, initial_value: Any = None):
        hooks = self.use_hooks()
        state, set_state = await hooks.use_state(key, initial_value)
        return state, set_state
    
    async def use_var(self, key: str, initial_value: Any = None):
        hooks = self.use_hooks()
        return await hooks.use_var(key, initial_value)
            
    async def delete_message(self, id: int):
        await self.history.delete_message(id=id)
        
    def messages_to_blocks(self, messages: List[ChatbotMessage]):
        blocks = []
        for message in messages:
            if message.role == "assistant":
                blocks.append(
                    ResponseBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        action_calls=message.action_calls,
                        id="history",
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
            elif message.role == "tool":
                blocks.append(
                    ActionBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        id="history",
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
            else:
                blocks.append(
                    TitleBlock(
                        db_msg_id=message.id,
                        content=message.content, 
                        role=message.role, 
                        id="history",
                        platform_id=message.platform_id,
                        created_at=message.created_at
                    ))
        return blocks
        
        
    async def last(self, limit=10):
        messages = await self.history.get_last_messages(limit)
        blocks = self.messages_to_blocks(messages)
        block_stream = BlockStream(self.history, blocks)
        return block_stream
    
    
    def last_messages(self, limit=10):
        return self.history.get_last_messages(limit)
    
    
    def clear_session(self):
        self.history.clear_session()
    