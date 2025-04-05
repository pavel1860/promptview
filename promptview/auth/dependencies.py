
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from promptview.auth.user_manager import  AuthManager, AuthModel
import os



BACKEND_SECRET = os.getenv("BACKEND_SECRET")

security = HTTPBearer()

async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    if credentials.credentials != BACKEND_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    return credentials.credentials



async def get_user_token(request: Request):
    session_token = request.cookies.get("next-auth.session-token")
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail="No session token found"
        )
    return session_token
    

    
    
def get_user_manager():
    return AuthManager()


async def get_auth_user(user_token: str = Depends(get_user_token), _: str = Depends(verify_api_key), user_manager: AuthManager = Depends(get_user_manager)):
    user =  await user_manager.get_user_by_session_token(user_token)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user

async def get_auth_admin_user(user: AuthModel = Depends(get_auth_user)):
    if not user.is_admin:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user
