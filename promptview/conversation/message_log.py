from pydantic import BaseModel, Field
import datetime as dt

from promptview.conversation.models import Branch, Message, MessageBackend, Session, Turn
from promptview.conversation.protocols import BaseProto







        
    

class MessageLogError(Exception):
    pass



class SessionManager:
    
    def __init__(self):
        self._backend = MessageBackend()
        
        
    async def get_session(self, user_id: str):
        return await self._backend.last_session(user_id=user_id)
    
    async def list_sessions(self, user_id: str):
        return await self._backend.list_sessions(user_id=user_id)
    
    async def create_session(self, user_id: str):
        session = await self._backend.add_session(Session(user_id=user_id))
        branch = await self._backend.add_branch(Branch(session_id=session.id, branch_order=0, message_counter=0))
        return session
        
    
    
    
    
class Head:
    
    def __init__(self):
        self.branch: Branch | None = None
        self.turn: Turn | None = None
        
    @property
    def is_initialized(self) -> bool:
        return self.branch is not None and self.turn is not None
    
    

class MessageLog:
    
    
    def __init__(self, backend: MessageBackend):
        self.head = Head()
        self._backend = backend
    
    @staticmethod
    async def from_user(user_id: str):
        backend = MessageBackend()
        session = await backend.last_session(user_id=user_id)
        if session is None:
            raise MessageLogError("No session found")
        message_log = MessageLog(backend)
        branch = await backend.get_branch(session_id=session.id, branch_order=0)
        if branch is None:
            raise MessageLogError("No branch found")
        message_log.head.branch = branch
        turn = await backend.get_last_turn(branch_id=branch.id)
        if turn is not None:
            message_log.head.turn = turn
        return message_log
        
    
    
    async def add_turn(self):
        if self.head.branch is None:
            raise MessageLogError("Branch is not initialized")
        turn = await self._backend.add_turn(Turn(branch_id=self.head.branch.id))
        self.head.turn = turn
        return turn
    
    async def append(self, message: Message):
        if self.head.branch is None:
            raise MessageLogError("Branch is not initialized")
        if self.head.turn is None:
            raise MessageLogError("Turn is not initialized")
        message.branch_id = self.head.branch.id
        message.turn_id = self.head.turn.id
        message.branch_order = self.head.branch.message_counter
        message = await self._backend.add_message(message)
        self.head.branch.message_counter += 1
        return message
    
    async def list_branches(self):
        pass
    
    async def checkout(self, branch: Branch | None = None):
        if branch is None:
            branch = await self.storage_backend.get_branch(is_main=True)
        self.head.branch = branch
        
    async def get_messages(self, limit: int = 10, offset: int = 0):
        count = 0
        if self.head.branch is None:
            raise MessageLogError("Branch is not initialized")
        all_msgs = []
        msgs = await self._backend.list_messages(branch_id=self.head.branch.id, limit=limit, offset=offset)
        all_msgs.extend(msgs)
        count += len(msgs)
        branch = self.head.branch        
        while count < limit:            
            if not branch.forked_from_branch_id:
                break            
            forked_from_message_order = branch.forked_from_message_order
            branch = await self._backend.get_branch_by_id(branch.forked_from_branch_id)
            if branch is None:
                raise MessageLogError("Branch not found")            
            msgs = await self._backend.list_messages(branch_id=branch.id, limit=limit-count, offset=0, max_order=forked_from_message_order)
            count += len(msgs)
            all_msgs.extend(msgs)
        return all_msgs

    # async def branch_from(self, message: Message, checkout: bool = True):
    #     if self.head.branch is None:
    #         raise MessageLogError("Branch is not initialized")
    #     branch = await self._backend.branch_from(session_id=self.head.branch.session_id, message=message)
    #     if checkout:
    #         self.head.branch = branch
    #         self.head.turn = None
    #     return branch
    
    async def branch_from(self, message: Message, checkout: bool = True):
        if self.head.branch is None:
            raise MessageLogError("Branch is not initialized")
        
        # branch = Branch(session_id=self.head.branch.session_id, forked_from_message_id=message.id)
        branch = Branch(
            session_id=self.head.branch.session_id, 
            forked_from_branch_id=message.branch_id, 
            forked_from_message_order=message.branch_order
        )
        branch = await self._backend.add_branch(branch)
        if checkout:
            self.head.branch = branch
            self.head.turn = None
        return branch
    
    async def commit(self, message: Message):
        pass

    
    async def update(self, message: Message):
        pass
    
    
    

    