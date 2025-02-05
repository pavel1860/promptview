import os
from typing import Generic, TypeVar, Optional, List, cast

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, func, insert, select, text, update
from .protocols import BranchProto, TurnProto, MessageProto  
from .alchemy_models import BranchModel, SessionModel, TurnModel, MessageModel, Base


import contextvars
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncSessionTransaction
from sqlalchemy.orm import sessionmaker
import datetime as dt
# Context variable to store the session
session_context = contextvars.ContextVar('session', default=None)

class SessionManager:
    def __init__(self, db_url: str | None = None):
        HISTORY_DB_URL = os.getenv("HISTORY_DB_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
        # Convert standard URL to async URL if needed
        if db_url is None:
            db_url = HISTORY_DB_URL
        if not db_url.startswith('postgresql+asyncpg://'):
            db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
            
        self._engine = create_async_engine(db_url)
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession
        )
    
    def _get_session(self) -> AsyncSession:
        session = session_context.get()
        if session is None:
            raise RuntimeError("No session found in context. Use SessionManager as context manager.")
        return session
        
    async def start(self) -> AsyncSession:
        session = self._session_factory()
        session_context.set(session)
        return session
    
    async def commit(self):
        session = self._get_session()
        await session.commit()
            
    async def rollback(self):
        session = self._get_session()        
        await session.rollback()
            
    async def close(self):
        session = self._get_session()
        await session.close()
        session_context.set(None)
        
    def add(self, model: "PGModel"):
        session = self._get_session()
        session.add(model._model)
    
    def add_all(self, models: list["PGModel"]):
        session = self._get_session()
        session.add_all([m._model for m in models])
        
    async def insert(self, table, model: BaseModel):
        session = self._get_session()
        stmt = insert(table).values(model.model_dump())
        await session.execute(stmt)
        
    async def __aenter__(self) -> "SessionManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @staticmethod
    def get_session() -> AsyncSession:
        """Get the current session from context"""
        session = session_context.get()
        if session is None:
            raise RuntimeError("No session found in context. Use SessionManager as context manager.")
        return session
    
HISTORY_DB_URL = os.getenv("HISTORY_DB_URL", "postgresql+asyncpg://snack:Aa123456@localhost:5432/snackbot")

engine = create_async_engine(HISTORY_DB_URL, echo=True, future=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)



# async def instantiate_all_models():    
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             await session.run_sync(Base.metadata.create_all)

# async def drop_all_models():
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             await session.run_sync(Base.metadata.drop_all)


async def instantiate_all_models():    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def drop_all_models():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)



EmptyID = -1


T = TypeVar("T")





class PGModel(Generic[T]):
    created_at: dt.datetime
    
    _model_type: type[T]
    _model: T

    def __init__(self, model_type: type[T], model: T | None = None, **kwargs):
        self._model_type = model_type
        if model is None:
            # Remove id from kwargs if it's not provided
            kwargs = {k: v for k, v in kwargs.items() if v is not None}
            self._model = self._model_type(**kwargs)
        else:
            self._model = model
            
        
    async def flush(self):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(self._model)
                # await session.commit()
                await session.flush()
                self.id = self._model.id
                return self
 
 
      


class Branch2(BranchProto):
    
    def to_dict(self) -> dict:
        data = self.model_dump(exclude={"id"}, exclude_none=True)
        return data

    @staticmethod
    async def get(id: int | None = None, forked_from_message_id: int | None = None, forked_from_message_order: int | None = None, is_main: bool = False) -> "Branch":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(BranchModel)
                if id is not None:
                    stmt = stmt.where(BranchModel.id == id)
                if forked_from_message_id is not None:
                    stmt = stmt.where(BranchModel.forked_from_message_id == forked_from_message_id)
                if forked_from_message_order is not None:
                    stmt = stmt.where(BranchModel.forked_from_message_order == forked_from_message_order)
                if is_main:
                    stmt = stmt.where(BranchModel.forked_from_message_id == None)
                    # Get the first branch created (main branch)
                    stmt = stmt.order_by(BranchModel.created_at.asc()).limit(1)
                branch = (await session.execute(stmt)).scalar_one_or_none()
                if branch is None:
                    return None
                return Branch(**branch.__dict__)
        
    async def save(self) -> "Branch":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(BranchModel).values(self.to_dict())
                res = await session.execute(stmt)
                self.id = res.inserted_primary_key[0]
                return self
            
    
    async def get_messages(self, limit: int = 10, offset: int = 0, is_desc: bool = True) -> list["MessageProto"]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = (
                    select(MessageModel, TurnModel)
                    .join(TurnModel, MessageModel.turn_id == TurnModel.id)
                    .where(MessageModel.branch_id == self.id)
                    .order_by(MessageModel.created_at.desc() if is_desc else MessageModel.created_at.asc())
                    .limit(limit)
                    .offset(offset)
                )
                res = await session.execute(stmt)
                return [
                    Message(
                        **message.__dict__,
                        branch=self,
                        turn=Turn(**message.turn.__dict__, branch=self)
                    )
                    for message in res.scalars()
                ]
            
    async def get_turns(self, limit: int = 10, offset: int = 0) -> list["TurnProto"]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(TurnModel).where(TurnModel.branch_id == self.id).order_by(TurnModel.created_at.desc()).limit(limit).offset(offset)
                res = await session.execute(stmt)
                return [Turn(**turn.__dict__) for turn in res.scalars()]
            
    

class Turn2(TurnProto):
    
    
    # @staticmethod
    # async def get(id: int | None = None, branch: BranchProto | None = None, limit: int = 10, offset: int = 0, is_desc: bool = True) -> "Turn":
    #     async with AsyncSessionLocal() as session:
    #         async with session.begin():
    #             if id is not None:
    #                 turn_rec = await session.get(TurnModel, id)
    #                 if turn_rec is None:
    #                     raise ValueError(f"Turn with id {id} not found")
    #             else:
    #                 stmt = select(TurnModel)
    #                 if branch is not None:
    #                     stmt = stmt.where(TurnModel.branch_id == branch.id)
    #                 stmt = stmt.order_by(TurnModel.created_at.desc() if is_desc else TurnModel.created_at.asc())
    #                 stmt = stmt.limit(limit).offset(offset)
    #                 turn_rec = (await session.execute(stmt)).scalar_one_or_none()
    #                 if turn_rec is None:
    #                     raise ValueError("No turns found matching criteria")

    #             # Refresh relationships
    #             await session.refresh(turn_rec, ["branch", "messages"])
    #             if turn_rec.branch is None:
    #                 raise ValueError(f"Turn {turn_rec.id} has no associated branch")

    #             branch = Branch(**turn_rec.branch.__dict__)
    #             messages = await Message.get_many(
    #                 branch=branch,
    #                 turn=turn_rec,
    #                 limit=limit,
    #                 offset=offset
    #             )

    #             return Turn(
    #                 **(turn_rec.__dict__ | {"branch": branch} | {"messages": messages}),
    #             )
    
    @staticmethod
    async def get(id: int | None = None, branch: BranchProto | None = None, limit: int = 10, offset: int = 0, is_desc: bool = True) -> "Turn":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(TurnModel)
                if id is not None:
                    stmt = stmt.where(TurnModel.id == id)
                if branch is not None:
                    stmt = stmt.where(TurnModel.branch_id == branch.id)
                stmt = stmt.order_by(TurnModel.created_at.desc() if is_desc else TurnModel.created_at.asc())
                stmt = stmt.limit(limit).offset(offset)
                turn_rec = (await session.execute(stmt)).scalar_one_or_none()
                if turn_rec is None:
                    raise ValueError("No turns found matching criteria")
                await session.refresh(turn_rec, ["branch", "messages"])
                branch = Branch(**turn_rec.branch.__dict__)
                messages = await Message.get_many(branch=branch, turn=turn_rec, limit=limit, offset=offset)
                return Turn(
                    **(turn_rec.__dict__ | {"branch": branch} | {"messages": messages}),
                )
    
    def to_dict(self) -> dict:
        data = self.model_dump(exclude={"id", "branch", "messages"}, exclude_none=True)
        if self.branch is not None:
            if not self.branch.id:
                raise ValueError("Branch has no id")
            data["branch_id"] = self.branch.id
        return data
    
    async def save(self) -> "Turn":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(TurnModel).values(self.to_dict())
                res = await session.execute(stmt)
                self.id = res.inserted_primary_key[0]
                return self
            
    async def get_messages(self, limit: int = 10, offset: int = 0) -> list["MessageProto"]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(MessageModel).where(MessageModel.turn_id == self.id).order_by(MessageModel.created_at.desc()).limit(limit).offset(offset)
                res = await session.execute(stmt)
                return [Message(**{**message.__dict__, "branch": self.branch, "turn": self}) for message in res.scalars()]
     
     
            
class Message2(MessageProto):  
    
    
    
    def to_dict(self) -> dict:
        data = self.model_dump(exclude={"id", "branch", "turn"}, exclude_none=True)
        if self.branch is not None:
            if not self.branch.id:
                raise ValueError("Branch has no id")
            data["branch_id"] = self.branch.id
        if self.turn is not None:
            if not self.turn.id:
                raise ValueError("Turn has no id")
            data["turn_id"] = self.turn.id
        return data

    
    @staticmethod
    async def get(id: int) -> "Message":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                message = await session.get(MessageModel, id)
                return Message(
                    **message.__dict__
                )
                
    @staticmethod
    async def get_many(branch: BranchProto | None = None, turn: TurnProto | None = None, limit: int = 10, offset: int = 0) -> list["Message"]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(MessageModel)
                if branch is not None:
                    stmt = stmt.where(MessageModel.branch_id == branch.id)
                if turn is not None:
                    stmt = stmt.where(MessageModel.turn_id == turn.id)
                stmt = stmt.order_by(MessageModel.created_at.desc()).limit(limit).offset(offset)
                res = await session.execute(stmt)
                return [Message(**message.__dict__) for message in res.scalars()]
        
    async def save(self) -> "Message":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(MessageModel).values(self.to_dict())
                res = await session.execute(stmt)
                self.id = res.inserted_primary_key[0]
                return self
            



            
            
            
class Session(BaseModel):
    _id: int | None = None
    created_at: dt.datetime = Field(default_factory=dt.datetime.now)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.now)
    user_id: str = Field(...)
    
    branches: list["Branch"] = Field(default_factory=list)
    
    class Config:
        arbitrary_types_allowed = True
    
    # def __init__(self, id: int | None = None, **kwargs):
    #     super().__init__(**kwargs)
    #     if id is not None:
    #         self._id = id
    #     if self.branches is None:
    #         self.branches = []
    
    @property
    def id(self) -> int:
        if self._id is None:
            raise ValueError("Session has no id")
        return self._id
    
    @id.setter
    def id(self, value: int):
        self._id = value
    


class Branch(BaseModel):
    _id: int | None = None
    created_at: dt.datetime = Field(default_factory=dt.datetime.now)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.now)
    message_counter: int = Field(0, ge=0)
    branch_order: int = Field(0, ge=0)
    forked_from_message_id: int | None = Field(default=None)
    forked_from_message_order: int | None = Field(default=None)    
    
    session_id: int | None = Field(default=None)
    
    def __init__(self, id: int | None = None, **kwargs):
        super().__init__(**kwargs)
        if id is not None:
            self._id = id
    
    @property
    def id(self) -> int:
        if self._id is None:
            raise ValueError("Branch has no id")
        return self._id
    
    @property
    def session(self) -> int | None:
        return self.session_id
    
    @property
    def forked_from_message(self) -> int | None:
        return self.forked_from_message_id
    
    
    def to_dict(self) -> dict:
        data = self.model_dump(exclude={"id"}, exclude_none=True)
        data["session_id"] = self.session
        if self.session is not None:
            data["session_id"] = self.session
        return data
    
    
class Turn(BaseModel):
    _id: int | None = None
    created_at: dt.datetime = Field(default_factory=dt.datetime.now)
    updated_at: dt.datetime = Field(default_factory=dt.datetime.now)
    local_state: dict = Field(default_factory=dict)    
    
    branch_id: int | None = Field(default=None)
    
    def __init__(self, id: int | None = None, **kwargs):
        super().__init__(**kwargs)
        if id is not None:
            self._id = id
    
    @property
    def id(self) -> int:
        if self._id is None:
            raise ValueError("Turn has no id")
        return self._id
    
    @property
    def branch(self) -> int:
        if self.branch_id is None:
            raise ValueError("Turn has no branch")
        return self.branch_id

class Message(BaseModel):
    _id: int | None = None
    created_at: dt.datetime = Field(default_factory=dt.datetime.now)
    role: str = Field(...)
    name: str = Field(...)
    content: str = Field(...)
    blocks: list[dict] | None = Field(default=None)
    run_id: str | None = Field(default=None)
    platform_id: str | None = Field(default=None)
    ref_id: str | None = Field(default=None)
    branch_order: int | None = Field(default=None)
    branch_id: int | None = Field(default=None)
    turn_id: int | None = Field(default=None)
    
    def __init__(self, id: int | None = None, **kwargs):
        super().__init__(**kwargs)
        if id is not None:
            self._id = id
    
    @property
    def id(self) -> int:
        if self._id is None:
            raise ValueError("Message has no id")
        return self._id
    
    @property
    def branch(self) -> int:
        if self.branch_id is None:
            raise ValueError("Message has no branch")
        return self.branch_id
    
    @property
    def turn(self) -> int:
        if self.turn_id is None:
            raise ValueError("Message has no turn")
        return self.turn_id
            



def pack_session(session: SessionModel) -> Session:
    obj = Session(**session.__dict__)
    obj._id = session.id
    return obj

def pack_branch(branch: BranchModel) -> Branch:
    obj = Branch(**branch.__dict__)
    obj._id = branch.id
    return obj
            
def pack_turn(turn: TurnModel) -> Turn:
    obj = Turn(**turn.__dict__)
    obj._id = turn.id
    return obj
            
def pack_message(message: MessageModel) -> Message:
    obj = Message(**message.__dict__)
    obj._id = message.id
    return obj
            
            
            
class MessageBackend:
    
    
    async def add_session(self, session: Session):
        async with AsyncSessionLocal() as conn:
            async with conn.begin():
                stmt = insert(SessionModel).values(session.model_dump(exclude={"id", "branches"}))
                res = await conn.execute(stmt)
                session._id = res.inserted_primary_key[0]
                await conn.commit()
                return session
    
    async def get_session(self, id: int | None = None, user_id: str | None = None) -> "Session":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(SessionModel, BranchModel).join(BranchModel, SessionModel.id == BranchModel.session_id)
                if id is not None:
                    stmt = stmt.where(SessionModel.id == id)
                if user_id is not None:
                    stmt = stmt.where(SessionModel.user_id == user_id)
                res = await session.execute(stmt)
                return Session(
                    **res.scalar_one().__dict__,
                    branches=[Branch(**branch.__dict__) for branch in res.scalars()]
                )
                
                
    async def list_sessions(self, user_id: str, limit: int = 10, offset: int = 0, is_desc: bool = True) -> list[Session]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = (
                    select(SessionModel)
                    .where(SessionModel.user_id == user_id)
                    .order_by(SessionModel.created_at.desc() if is_desc else SessionModel.created_at.asc())
                    .limit(limit)
                    .offset(offset)
                )
                res = await session.execute(stmt)
                scalars = list(res.scalars())
                return [pack_session(session) for session in scalars]

            
    async def last_session(self, user_id: str) -> Session | None:
        sessions = await self.list_sessions(user_id, limit=1, offset=0, is_desc=False)
        if len(sessions) == 0:
            return None
        return sessions[0]
    
    async def create_session_by_user_id(self, user_id: str) -> Session:
        session = SessionModel(user_id=user_id)
        session = await self.add_session(session)
        return Session(**session.__dict__)
                
    async def get_branch(self, session_id: int, branch_order: int) -> Branch | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(BranchModel).where(BranchModel.session_id == session_id, BranchModel.branch_order == branch_order)
                res = await session.execute(stmt)
                branch = Branch(**res.scalar_one().__dict__)
                branch._id = branch.id
                return branch
            
    async def list_branches(self, session_id: int) -> list[Branch]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(BranchModel).where(BranchModel.session_id == session_id)
                res = await session.execute(stmt)
                return [pack_branch(branch) for branch in res.scalars()]
            
    async def get_branch_by_id(self, branch_id: int) -> Branch | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(BranchModel).where(BranchModel.id == branch_id)
                res = await session.execute(stmt)
                return pack_branch(res.scalar_one())
            
    async def add_branch(self, branch: Branch):
        async with AsyncSessionLocal() as conn:
            async with conn.begin():
                # stmt = select(BranchModel).where(BranchModel.session_id == branch.session)
                # res = await conn.execute(stmt)
                # session = res.scalar_one()
                stmt = select(func.count(BranchModel.id)).where(BranchModel.session_id == branch.session)
                num_branches = await conn.scalar(stmt)
                if num_branches is None:
                    raise ValueError("Session not found")            
                branch.branch_order = num_branches
                stmt = insert(BranchModel).values(branch.model_dump())
                res = await conn.execute(stmt)
                branch._id = res.inserted_primary_key[0]
                await conn.commit()
                return branch
            
    async def update_branch(self, **kwargs):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = update(BranchModel).values(**kwargs)
                res = await session.execute(stmt)
                await session.commit()
                return res.scalar_one()
            
    async def get_turn(self, id: int) -> Turn | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(TurnModel).where(TurnModel.id == id)
                res = await session.execute(stmt)
                return pack_turn(res.scalar_one())

    async def add_turn(self, turn: Turn):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(TurnModel).values(turn.model_dump())
                res = await session.execute(stmt)
                turn._id = res.inserted_primary_key[0]
                await session.commit()
                return turn
    
    async def list_turns(self, branch_id: int, limit: int = 10, offset: int = 0, is_desc: bool = True) -> list[Turn]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = (
                    select(TurnModel)
                    .where(TurnModel.branch_id == branch_id)
                    .order_by(TurnModel.created_at.desc() if is_desc else TurnModel.created_at.asc())
                    .limit(limit)
                    .offset(offset)
                )
                res = await session.execute(stmt)
                return [pack_turn(turn) for turn in res.scalars()]
            
    async def get_last_turn(self, branch_id: int) -> Turn | None:
        turns = await self.list_turns(branch_id, limit=1, offset=0, is_desc=False)
        if len(turns) == 0:
            return None
        return turns[0]

    async def get_message(self, id: int) -> Message | None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = select(MessageModel).where(MessageModel.id == id)
                res = await session.execute(stmt)
                return pack_message(res.scalar_one())
            
    async def list_messages(self, branch_id: int, limit: int = 10, offset: int = 0, is_desc: bool = True, max_order: int | None = None) -> list[Message]:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = (
                    select(MessageModel)
                    .where(MessageModel.branch_id == branch_id)
                )
                if max_order is not None:
                    stmt = stmt.where(MessageModel.branch_order <= max_order)
                    
                stmt = stmt.order_by(MessageModel.created_at.desc() if is_desc else MessageModel.created_at.asc())
                stmt = stmt.limit(limit)
                stmt = stmt.offset(offset)
                res = await session.execute(stmt)
                return [pack_message(message) for message in res.scalars()]

                
    async def add_message(self, message: Message):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(MessageModel).values(message.model_dump())
                res = await session.execute(stmt)
                stmt_branch = update(BranchModel).where(BranchModel.id == message.branch_id).values(message_counter=BranchModel.message_counter + 1)
                res_branch =await session.execute(stmt_branch)
                message._id = res.inserted_primary_key[0]
                await session.commit()
                return message
            
    async def branch_from(self, session_id: int, message: Message) -> Branch:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                stmt = insert(BranchModel).values({
                    "session_id": session_id,
                    "forked_from_message_id": message.id,
                    "forked_from_message_order": message.branch_order,
                })
                res = await session.execute(stmt)
                branch = Branch(**res.scalar_one().__dict__)
                branch._id = branch.id
                return branch
        
        
    # async def add_message(self, message: Message):
    #     async with AsyncSessionLocal() as session:
    #         async with session.begin():
    #             stmt = text("""
    #             WITH updated_branch AS (
    #                 UPDATE branches 
    #                 SET message_counter = message_counter + 1
    #                 WHERE id = :branch_id
    #                 RETURNING message_counter - 1 as new_order
    #             )
    #             INSERT INTO messages (
    #                 created_at, updated_at, role, name, content, blocks, 
    #                 run_id, platform_id, ref_id, branch_order, branch_id, turn_id
    #             )
    #             SELECT 
    #                 :created_at, :updated_at, :role, :name, :content, :blocks,
    #                 :run_id, :platform_id, :ref_id, new_order, :branch_id, :turn_id
    #             FROM updated_branch
    #             RETURNING id, created_at, updated_at, role, name, content, blocks, run_id, platform_id, ref_id, branch_order, branch_id, turn_id
    #             """)
                
    #             values = {
    #                 # **message.model_dump(exclude={'_id'}),
    #                 'created_at': message.created_at, 
    #                 'updated_at': message.created_at,
    #                 'role': message.role,
    #                 'name': message.name,
    #                 'content': message.content,
    #                 'blocks': message.blocks,
    #                 'run_id': message.run_id,
    #                 'platform_id': message.platform_id,
    #                 'ref_id': message.ref_id,
    #                 'branch_order': message.branch_order,
    #                 'branch_id': message.branch,
    #                 'turn_id': message.turn,
    #             }
    #             res = await session.execute(stmt, values)
    #             row = res.fetchone()
    #             message._id = row.id
    #             await session.commit()
    #             return message
                
    
