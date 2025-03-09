
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from promptview.auth.dependencies import get_auth_admin_user, get_auth_user, get_user_manager, verify_api_key
from promptview.auth.user_manager import UserAuthPayload, UserManager, UserModel
import os






router = APIRouter(
    prefix="/auth",
    tags=["manager"],
    # dependencies=[Depends(get_current_user), ]
)



@router.post("/create_user")
async def create_user(payload: UserAuthPayload, user_manager: UserManager = Depends(get_user_manager), api_key: str = Depends(verify_api_key)):
    return await user_manager.create_user(payload)


class UserIdPayload(BaseModel):
    id: int

@router.post("/get_user")
async def get_user_by_id(payload: UserIdPayload, user_manager: UserManager = Depends(get_user_manager), api_key: str = Depends(verify_api_key)):
    return await user_manager.get_user(payload.id)


@router.post("/test")
async def test(user: UserModel = Depends(get_auth_user)):
    print(user)
    return {"message": "Hello, World!"}



@router.get("/users")
async def get_users(user: UserModel = Depends(get_auth_admin_user), user_manager: UserManager = Depends(get_user_manager)):
    return await user_manager.get_users()



