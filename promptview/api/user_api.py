from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, create_model
from typing import List, Optional, Type
import datetime as dt
from sqlalchemy import inspect

from promptview.conversation.message_log import UserManager
from promptview.conversation.models import User, Session, Message, UserBackend
from promptview.conversation.alchemy_models import BaseUserModel

def create_user_router(user_model_cls: Type[BaseUserModel]):
    # Dynamically create UserCreate model based on user_model_cls columns
    mapper = inspect(user_model_cls)
    fields = {}
    for column in mapper.columns:
        if column.name not in ['id', 'created_at', 'updated_at', 'type']:
            python_type = column.type.python_type
            if column.nullable:
                fields[column.name] = (Optional[python_type], None)
            else:
                fields[column.name] = (python_type, ...)
    
    # Add type field with default value from user_model_cls
    fields['type'] = (str, user_model_cls.__mapper_args__['polymorphic_identity'])
    
    UserCreate = create_model('UserCreate', **fields)

    class UserResponse(BaseModel):
        id: int
        created_at: dt.datetime
        updated_at: dt.datetime
        type: str
        # Dynamically add fields from user_model_cls
        __annotations__ = {
            'id': int,
            'created_at': dt.datetime,
            'updated_at': dt.datetime,
            'type': str,
            **{column.name: Optional[column.type.python_type] 
               for column in mapper.columns 
               if column.name not in ['id', 'created_at', 'updated_at', 'type']}
        }

        class Config:
            from_attributes = True

    class SessionResponse(BaseModel):
        id: int
        created_at: dt.datetime
        updated_at: dt.datetime
        user_id: str

        class Config:
            from_attributes = True

    class MessageResponse(BaseModel):
        id: int
        created_at: dt.datetime
        role: str
        name: str
        content: str
        branch_order: int | None
        branch_id: int | None
        turn_id: int | None

        class Config:
            from_attributes = True

    # Router setup
    router = APIRouter(prefix="/users", tags=["users"])

    # Dependency for UserManager instance with specific user model
    async def get_user_manager() -> UserManager:
        return UserManager(backend=UserBackend(user_model_cls=user_model_cls))

    @router.post("/", response_model=UserResponse)
    async def create_user(
        user_data: UserCreate,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> User:
        try:
            return await user_manager.create_user(**user_data.model_dump())
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{user_id}", response_model=UserResponse)
    async def get_user(
        user_id: int,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> User:
        try:
            user = await user_manager.get_user(user_id=user_id)
            if user is None:
                raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")
            return user
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/", response_model=List[UserResponse])
    async def list_users(
        limit: int = 10,
        offset: int = 0,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> List[User]:
        try:
            users = await user_manager.list_users(limit=limit, offset=offset)
            return users
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{user_id}/sessions", response_model=SessionResponse)
    async def create_user_session(
        user_id: int,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> Session:
        try:
            return await user_manager.add_session(user_id=user_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{user_id}/sessions", response_model=List[SessionResponse])
    async def list_user_sessions(
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> List[Session]:
        try:
            return await user_manager.list_user_sessions(user_id=user_id, limit=limit, offset=offset)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{user_id}/messages", response_model=List[MessageResponse])
    async def get_user_messages(
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> List[Message]:
        try:
            return await user_manager.get_user_messages(user_id=user_id, limit=limit, offset=offset)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
            
    return router 