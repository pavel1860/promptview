
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from promptview.auth.user_manager import UserAuthPayload, UserManager, UserModel
import os

BACKEND_SECRET = os.getenv("BACKEND_SECRET")


security = HTTPBearer()

router = APIRouter(
    prefix="/auth",
    tags=["manager"],
    # dependencies=[Depends(get_current_user), ]
)


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != BACKEND_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return credentials.credentials

class UserIdPayload(BaseModel):
    id: int

async def get_user_token(request: Request, _: str = Depends(verify_api_key)):
    session_token = request.cookies.get("next-auth.session-token")
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="No session token found"
        )
    return session_token
    

    
    
def get_user_manager():
    return UserManager()


async def get_user(user_token: str = Depends(get_user_token), user_manager: UserManager = Depends(get_user_manager)):
    return await user_manager.get_user_by_session_token(user_token)

async def get_admin_user(user: UserModel = Depends(get_user)):
    if not user.is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

@router.post("/create_user")
async def create_user(payload: UserAuthPayload, user_manager: UserManager = Depends(get_user_manager), api_key: str = Depends(verify_api_key)):
    return await user_manager.create_user(payload)


@router.post("/get_user")
async def get_user_by_id(payload: UserIdPayload, user_manager: UserManager = Depends(get_user_manager), api_key: str = Depends(verify_api_key)):
    return await user_manager.get_user(payload.id)


@router.post("/test")
async def test(user: UserModel = Depends(get_user)):
    print(user)
    return {"message": "Hello, World!"}



@router.get("/users")
async def get_users(user: UserModel = Depends(get_admin_user), user_manager: UserManager = Depends(get_user_manager)):
    return await user_manager.get_users()



