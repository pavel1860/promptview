
from typing import Type, TypeVar
from uuid import UUID
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from promptview.auth.dependencies import get_auth_admin_user, get_auth_user, get_user_manager, verify_api_key
from promptview.auth.user_manager import UserAuthPayload, AuthManager, AuthModel
import os

from promptview.model2.model import Model




USER_MODEL = TypeVar('USER_MODEL', bound=AuthModel)



def create_auth_router(user_manager_cls: Type[AuthManager[USER_MODEL]]):
    
    def get_user_manager():
        return user_manager_cls()

    router = APIRouter(
        prefix="/auth",
        tags=["manager"],
        # dependencies=[Depends(get_current_user), ]
    )

    @router.post("/user/create")
    async def create_user(
        payload: UserAuthPayload, 
        request: Request, 
        user_manager: AuthManager = Depends(get_user_manager),
        anonymous_token: str | None = Cookie(None, alias="chatboard.anonymous-token"),
    ):
        
        anonymous_token = anonymous_token
        if anonymous_token:
            inst = await user_manager.create_user_from_anonymous(UUID(anonymous_token), payload, request)
            if inst is None:
                inst = await user_manager.create_user(payload, request)    
        elif payload.user_id:
            inst = await user_manager.get_user_model().query().where(user_id=payload.user_id).last()
            if inst is None:                
                inst = await user_manager.create_user(payload, request)
        return inst


    class UserIdPayload(BaseModel):
        id: int

    @router.get("/user/{id}")
    async def get_user_by_id(
        payload: UserIdPayload, 
        request: Request, 
        user_manager: AuthManager = Depends(get_user_manager)
    ):
        return await user_manager.get_by_id(payload.id)



    @router.get("/users")
    async def get_users(
        user: USER_MODEL = Depends(get_auth_admin_user), 
        user_manager: AuthManager = Depends(get_user_manager)
    ):
        return await user_manager.get_users()


    return router
