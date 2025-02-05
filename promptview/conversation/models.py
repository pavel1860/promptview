import os
from typing import Generic, TypeVar, Optional, List, cast

from sqlalchemy import create_engine
from .protocols import BranchProto, TurnProto, MessageProto  
from .alchemy_models import BranchModel, TurnModel, MessageModel, Base


import contextvars
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker, AsyncSessionTransaction
from sqlalchemy.orm import sessionmaker
import datetime as dt
# Context variable to store the session
session_context = contextvars.ContextVar('session', default=None)

# class SessionManager:
#     def __init__(self, db_url: str | None = None):
#         HISTORY_DB_URL = os.getenv("HISTORY_DB_URL", "postgresql://snack:Aa123456@localhost:5432/snackbot")
#         # Convert standard URL to async URL if needed
#         if db_url is None:
#             db_url = HISTORY_DB_URL
#         if not db_url.startswith('postgresql+asyncpg://'):
#             db_url = db_url.replace('postgresql://', 'postgresql+asyncpg://')
            
#         self._engine = create_async_engine(db_url)
#         self._session_factory = async_sessionmaker(
#             bind=self._engine,
#             expire_on_commit=False,
#             class_=AsyncSession
#         )
    
#     def _get_session(self) -> AsyncSession:
#         session = session_context.get()
#         if session is None:
#             raise RuntimeError("No session found in context. Use SessionManager as context manager.")
#         return session
        
#     async def start(self) -> AsyncSession:
#         session = self._session_factory()
#         session_context.set(session)
#         return session
    
#     async def commit(self):
#         session = self._get_session()
#         await session.commit()
            
#     async def rollback(self):
#         session = self._get_session()        
#         await session.rollback()
            
#     async def close(self):
#         session = self._get_session()
#         await session.close()
#         session_context.set(None)

#     async def __aenter__(self) -> AsyncSession:
#         return await self.start()

#     async def __aexit__(self, exc_type, exc_val, exc_tb):
#         await self.close()

#     @staticmethod
#     def get_session() -> AsyncSession:
#         """Get the current session from context"""
#         session = session_context.get()
#         if session is None:
#             raise RuntimeError("No session found in context. Use SessionManager as context manager.")
#         return session
    
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
        


class Branch(PGModel[BranchModel], BranchProto):
    def __init__(
        self,         
        created_at: dt.datetime | None = None, 
        forked_from_message: "Message | None" = None, 
        forked_from_message_order: int | None = None,
        branch: BranchModel | None = None, 
    ):
        super().__init__(
            BranchModel, 
            branch, 
            created_at=created_at, 
            forked_from_message=forked_from_message._model if forked_from_message else None, 
            forked_from_message_order=forked_from_message_order
        )
        # Initialize protocol attributes
        self.id: int = self._model.id if self._model.id is not None else EmptyID
        self.created_at: dt.datetime = self._model.created_at if self._model.created_at else dt.datetime.now()
        self.forked_from_message: Optional[MessageProto] = cast(MessageProto, Message(message=self._model.forked_from_message)) if self._model.forked_from_message else None
        self.forked_from_message_order: Optional[int] = self._model.forked_from_message_order
    
    @staticmethod
    async def get(id: int) -> "Branch":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                branch = await session.get(BranchModel, id)
                return Branch(branch=branch)
        
    async def save(self) -> "Branch":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(self._model)
                await session.commit()
                return self

class Turn(PGModel[TurnModel], TurnProto):
    def __init__(
        self,  
        created_at: dt.datetime | None = None, 
        branch: "Branch | None" = None,
        turn: TurnModel | None = None,
    ):
        super().__init__(
            TurnModel, 
            turn, 
            created_at=created_at, 
            branch=branch._model if branch else None
        )
        # Initialize protocol attributes
        self.created_at: dt.datetime = self._model.created_at if self._model.created_at else dt.datetime.now()
        self.branch: BranchProto = cast(BranchProto, Branch(branch=self._model.branch))
        self.messages: list[MessageProto] = [cast(MessageProto, Message(message=m)) for m in self._model.messages]
        self.local_state: dict = self._model.local_state if isinstance(self._model.local_state, dict) else {}
    
    @staticmethod
    async def get(id: int) -> "Turn":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                turn = await session.get(TurnModel, id)
                return Turn(turn=turn)
        
    async def save(self) -> "Turn":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(self._model)
                await session.commit()
                return self

class Message(PGModel[MessageModel], MessageProto):    
    def __init__(
        self, 
        created_at: dt.datetime | None = None,
        role: str | None = None,
        name: str | None = None,
        content: str | None = None,
        blocks: list[dict] | None = None,
        run_id: str | None = None,
        platform_id: str | None = None,
        ref_id: str | None = None,
        branch_order: int | None = None,
        branch: "Branch | None" = None,
        turn: "Turn | None" = None,
        message: MessageModel | None = None,
    ):
        super().__init__(
            MessageModel, 
            message,
            created_at=created_at,
            role=role or "user",
            name=name,
            content=content,
            blocks=blocks,
            run_id=run_id,
            platform_id=platform_id,
            ref_id=ref_id,
            branch_order=branch_order,
            branch=branch._model if branch else None,
            turn=turn._model if turn else None
        )
        # Initialize protocol attributes
        self.id: int = self._model.id if self._model.id is not None else EmptyID
        self.created_at: dt.datetime = self._model.created_at if self._model.created_at else dt.datetime.now()
        self.role: str = self._model.role or "user"
        self.name: Optional[str] = self._model.name
        self.content: str = self._model.content or ""
        self.blocks: Optional[List[dict]] = self._model.blocks
        self.run_id: str = str(self._model.run_id) if self._model.run_id else ""
        self.platform_id: Optional[str] = self._model.platform_id
        self.ref_id: Optional[str] = self._model.ref_id
        self.branch_order: int = self._model.branch_order if self._model.branch_order is not None else 0
        self.branch: BranchProto = cast(BranchProto, Branch(branch=self._model.branch))
        self.turn: TurnProto = cast(TurnProto, Turn(turn=self._model.turn))
    
    @staticmethod
    async def get(id: int) -> "Message":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                message = await session.get(MessageModel, id)
                return Message(message=message)
        
    async def save(self) -> "Message":
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(self._model)
                await session.commit()
                return self