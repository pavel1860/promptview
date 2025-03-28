
from typing import Type, TypeVar
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from promptview.auth.dependencies import get_auth_admin_user, get_auth_user, get_user_manager, verify_api_key
from promptview.auth.user_manager import UserAuthPayload, AuthManager, AuthModel
import os

from promptview.model2.model import Model




USER_MODEL = TypeVar('USER_MODEL', bound=AuthModel)



def create_auth_router(auth_model: Type[USER_MODEL]):

    router = APIRouter(
        prefix="/auth",
        tags=["manager"],
        # dependencies=[Depends(get_current_user), ]
    )

    @router.post("/create_user")
    async def create_user(payload: UserAuthPayload, api_key: str = Depends(verify_api_key)):
        inst = await auth_model(**payload.model_dump()).save()
        return inst


    class UserIdPayload(BaseModel):
        id: int

    @router.post("/get_user")
    async def get_user_by_id(payload: UserIdPayload, api_key: str = Depends(verify_api_key)):
        return await auth_model.get(payload.id)


    @router.post("/test")
    async def test(user: USER_MODEL = Depends(get_auth_user)):
        print(user)
        return {"message": "Hello, World!"}



    @router.get("/users")
    async def get_users(user: USER_MODEL = Depends(get_auth_admin_user), user_manager: AuthManager = Depends(get_user_manager)):
        return await user_manager.get_users()


    return router
