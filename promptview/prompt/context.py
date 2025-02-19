from abc import abstractmethod
import contextvars
from enum import Enum
from typing import Any, Generic, List, Type, TypeVar, Union, Dict

from promptview.artifact_log.artifact_log3 import ArtifactLog
from promptview.conversation.message_log import MessageLog, SessionManager
from promptview.conversation.models import Session
from promptview.model.model import Model
from ..llms.messages import ActionCall
from .block import ActionBlock, BaseBlock, BulletType, ListBlock, ResponseBlock, TitleBlock, TitleType, BlockRole
from .block2 import StrBlock  
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
        message_log: MessageLog, 
        blocks: List[StrBlock] | None = None, 
        run_id: str | None = None, 
        prompt_name: str | None = None
    ):
        self.message_log = message_log
        self._blocks = []
        self._block_lookup = defaultdict(list)        
        if blocks:
            for b in blocks:
                self.append(b)        
        self._dirty = True
        self.response = None
        self.run_id = run_id
        self.prompt_name = prompt_name
    
    
    def __add__(self, other: Union[list[StrBlock] , "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, StrBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.message_log, self._blocks + other, run_id=self.run_id, prompt_name=self.prompt_name)
        elif isinstance(other, BlockStream):
            return BlockStream(self.message_log, self._blocks + other._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        else:       
            raise ValueError(f"Invalid type: {type(other)}")
        
    def __radd__(self, other: Union[list[StrBlock], "BlockStream"]):
        if isinstance(other, list):
            for i, b in enumerate(other):
                if not isinstance(b, StrBlock):
                    raise ValueError(f"Invalid block type: {type(b)} at index {i}")
            return BlockStream(self.message_log, other + self._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        elif isinstance(other, BlockStream):
            return BlockStream(self.message_log, other._blocks + self._blocks, run_id=self.run_id, prompt_name=self.prompt_name)
        else:       
            raise ValueError(f"Invalid type: {type(other)}")        
    
        
    def _update_lookup(self, block: StrBlock):
        if isinstance(block, StrBlock):
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
                    StrBlock(
                        content=self.get(k["content"]),
                        role=k.get("role", "user")
                    )
                )
                
        return chat_blocks
        
        
    def block(self, title=None, ttype: TitleType="md", role: BlockRole = "user", name: str | None = None, id: str | None = None):
        lb = StrBlock(title=title, ttype=ttype, id=id, role=role, name=name)
        self.append(lb)
        return lb
    
    def list(self, title=None, ttype: TitleType="md", bullet: BulletType = "-", role: BlockRole = "user", name: str | None = None, id: str | None = None):        
        lb = ListBlock(title=title, ttype=ttype, bullet=bullet, id=id, role=role, name=name)
        self.append(lb)
        return lb
    
    async def push(self, block: BaseBlock | str | dict, action: ActionCall | None = None, role: BlockRole | None = None, id: str | None="history"):
        platform_id = None
        action_calls = None        
        if isinstance(block, str) or isinstance(block, dict):
            content = block    
            block = TitleBlock(content=block, role=role or "user", id=id)
            _role = role or "user"
        elif isinstance(block, BaseBlock):
            content = block.render()
            _role = role or block.role or "user"
            if action:
                platform_id = action.id
            if isinstance(block, ResponseBlock):
                action_calls = [a.model_dump() for a in block.action_calls]
        else:
            raise ValueError(f"Invalid block type: {type(block)}")
        message = Message(
            content=content,
            role=_role,
            name=id,
            platform_id=platform_id,
            extra={"action_calls": action_calls}
        )        
        message = await self.message_log.append(message)
        block.db_msg_id = message.id
        self.append(block)
        return message
    
    
        
    async def commit_turn(self):
        await self.message_log.commit()

    async def delete(self, block: BaseBlock):
        if block.db_msg_id:
            await self.message_log.delete_message(id=block.db_msg_id)
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
    
    
MODEL = TypeVar("MODEL", bound=Model)
class ContextBase(Generic[MODEL]):
    _model: Type[MODEL]
    _artifact_log: ArtifactLog
    _head_id: int
    _branch_id: int | None
    _initialized: bool
    inputs: dict
    _ctx_token: contextvars.Token | None
    _hooks: TurnHooks | None
    run_id: str | None
    prompt_name: str
    
    def __init__(
        self, 
        head_id: int,
        branch_id: int | None = None,
        inputs: dict | None = None, 
        artifact_log: ArtifactLog | None = None,
        prompt_name: str = "global",
        run_id: str | None = None,
        commit_on_exit: bool = False,
    ):
        self._head_id = head_id
        self._branch_id = branch_id
        self._artifact_log = artifact_log or ArtifactLog(head_id=head_id, branch_id=branch_id)
        self._initialized = False
        self.inputs = inputs or {}
        self._ctx_token = None
        self._hooks = None
        self.tracer = None
        self._parent_ctx = None
        self.prompt_name = prompt_name
        self.run_id = run_id
        self._init_method: Dict[str, Any] | None = None
        self._commit_on_exit = commit_on_exit
    
    @property
    def artifact_log(self):
        if self._artifact_log is None:
            raise ValueError("Artifact log not set")
        return self._artifact_log
        
    def build_child(self, prompt_name: str):
        ctx = ContextBase(
            head_id=self.head_id,
            branch_id=self.branch_id,
            inputs=self.inputs, 
            artifact_log=self._artifact_log,
            prompt_name=prompt_name,
            run_id=self.run_id
        )
        ctx._parent_ctx = self        
        ctx._initialized = self._initialized
        # ctx._hooks = TurnHooks(self._artifact_log, prompt_name=prompt_name)
        return ctx
    

    @staticmethod
    def get_current():
        try:
            return CURR_CONTEXT.get()
        except LookupError:
            return None
    
    @property
    def session(self):
        if self._session is None:
            raise ValueError("Session not set")
        return self._session
    
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
        if self.session is None:
            raise ValueError("Session not set")
        return self.session.id
    
    @property
    def head(self):
        return self._artifact_log.head
    
    @property
    def head_id(self):
        return self._artifact_log.head["id"]
    
    @property
    def branch_id(self):
        return self._artifact_log.head["branch_id"]
    
    @property
    def turn_id(self):
        return self._artifact_log.head["id"]
    
    @property
    def turn(self):
        return self._artifact_log.head["id"]
    
    @property
    def branch(self):
        return self._artifact_log.head["branch_id"]
    
    
    @property
    def is_initialized(self):
        return self._initialized
    
        
    async def get_last_messages(self, limit: int = 10):
        return await self.message_log.get_messages(limit)
    
    
    def resume_session(self, session_id: int, branch_id: int | None = None, new_turn: bool = True):
        self._init_method = {
            "type": InitMethod.RESUME_SESSION,
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
    
    # async def _resume(self, new_turn: bool = True):        
    #     # await self.history.init_last_session()        
    #     self._session = await self._session_manager.get_last_user_session(user_id=self.user_id)
    #     self._message_log = await MessageLog.from_user_last_session(self.user_id)
    #     if self.branch_id:
    #         await self.message_log.switch_to(self.branch_id)
    #     self._initialized = True
    #     if new_turn:
    #         await self.message_log.add_turn()
    #     self._hooks = TurnHooks(self.message_log, prompt_name=self.prompt_name)
    #     return self
    
    # async def _start(self):
    #     # await self.history.init_new_session()        
    #     self._session = await self._session_manager.create_session(self.user_id)
    #     self._message_log = await MessageLog.from_session(self.session.id)
    #     await self.message_log.add_turn()
    #     self._initialized = True
    #     self._hooks = TurnHooks(self.message_log, prompt_name=self.prompt_name)
    #     return self
    
    # async def _resume_session(self, session_id: int, branch_id: int | None = None, new_turn: bool = True):
    #     self._session = await self._session_manager.get_session(session_id=session_id)
    #     self._message_log = await MessageLog.from_session(session_id)
    #     if branch_id:
    #         await self.message_log.switch_to(branch_id)
    #     self._initialized = True
    #     if new_turn:
    #         await self.message_log.add_turn()
    #     self._hooks = TurnHooks(self.message_log, prompt_name=self.prompt_name)
    #     return self
        
    # async def __aenter__(self):
    #     if not self._initialized:
    #         if not self._init_method:
    #             raise ValueError("Init method not set. Call resume() or start() first.")
    #         if self._init_method["type"] == InitMethod.RESUME:
    #             await self._resume(**self._init_method["kwargs"])
    #         elif self._init_method["type"] == InitMethod.START:
    #             await self._start()
    #         elif self._init_method["type"] == InitMethod.RESUME_SESSION:
    #             await self._resume_session(**self._init_method["kwargs"])
            
    #     self.set_context()
    #     return self
    
    async def __aenter__(self):
        if not self._artifact_log.is_initialized:
            await self._artifact_log.init_head(head_id=self._head_id, branch_id=self._branch_id)
            self._artifact_log.set_context()
        self.set_context()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        # await self.commit()
        if self._commit_on_exit:
            await self.commit()
        self.reset_context()
        
    def use_hooks(self, prompt_name: str | None = None) -> TurnHooks:
        return TurnHooks(self.message_log, prompt_name or self.prompt_name)
    
    async def use_state(self, key: str, initial_value: Any = None):
        hooks = self.use_hooks()
        state, set_state = await hooks.use_state(key, initial_value)
        return state, set_state
    
    async def use_var(self, key: str, initial_value: Any = None):
        hooks = self.use_hooks()
        return await hooks.use_var(key, initial_value)
            
    # async def delete_message(self, id: int):
        # await self.message_log.delete_message(id=id)
    
    @abstractmethod
    def model_to_blocks(self, model: MODEL) -> StrBlock:
        pass
    
    
    async def commit(self):
        await self.artifact_log.commit_turn()
      
    # def messages_to_blocks(self, messages: List[Message]):
    #     blocks = []
    #     for message in messages:
    #         if message.role == "assistant":
    #             blocks.append(
    #                 ResponseBlock(
    #                     db_msg_id=message.id,
    #                     content=message.content, 
    #                     action_calls=message.extra.get("action_calls", []),
    #                     id="history",
    #                     platform_id=message.platform_id,
    #                     created_at=message.created_at
    #                 ))
    #         elif message.role == "tool":
    #             blocks.append(
    #                 ActionBlock(
    #                     db_msg_id=message.id,
    #                     content=message.content, 
    #                     id="history",
    #                     platform_id=message.platform_id,
    #                     created_at=message.created_at
    #                 ))
    #         else:
    #             blocks.append(
    #                 TitleBlock(
    #                     db_msg_id=message.id,
    #                     content=message.content, 
    #                     role=message.role, 
    #                     id="history",
    #                     platform_id=message.platform_id,
    #                     created_at=message.created_at
    #                 ))
    #     return blocks
        
        
    async def last(self, limit=10):
        records = await self._model.limit(limit).order_by("created_at")
        blocks = [self.model_to_blocks(r) for r in records]
        # block_stream = BlockStream(self.message_log, blocks)
        return blocks
    
    
    # def last_messages(self, limit=10):
        # return self.message_log.get_messages(limit)
    
    
    # def clear_session(self):
        # self.message_log.clear_session()
    