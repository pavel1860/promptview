from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field, create_model
from typing import List, Optional, Type
import datetime as dt

from promptview.conversation.message_log import UserManager
from promptview.conversation.models import User, Session, Message, UserBackend
from promptview.conversation.alchemy_models import BaseUserModel

def create_user_router(user_model_cls: Type[User], backend: UserBackend):
    # Create UserCreate model by excluding auto-generated fields from user_model_cls
    UserCreate = create_model(
        'UserCreate',
        __base__=user_model_cls,
        id=(Optional[int], None),
        created_at=(Optional[dt.datetime], None),
        updated_at=(Optional[dt.datetime], None),
    )

    class UserResponse(user_model_cls):
        id: int
        class Config:
            from_attributes = True

    def to_response(user: User) -> dict:
        data = user.model_dump()
        data["id"] = user.id
        return data

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
        return UserManager(backend=backend)

    @router.post("/", response_model=UserResponse)
    async def create_user(
        user_data: UserCreate,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> dict:
        try:
            user = await user_manager.create_user(**user_data.model_dump(exclude={'id', 'created_at', 'updated_at'}))
            return to_response(user)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/{user_id}", response_model=UserResponse)
    async def get_user(
        user_id: int,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> dict:
        user = await user_manager.get_user(user_id=user_id)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User with id {user_id} not found")
        try:
            return to_response(user)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/", response_model=List[UserResponse])
    async def list_users(
        limit: int = 10,
        offset: int = 0,
        user_manager: UserManager = Depends(get_user_manager)
    ) -> List[dict]:
        try:
            users = await user_manager.list_users(limit=limit, offset=offset)
            return [to_response(user) for user in users]
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