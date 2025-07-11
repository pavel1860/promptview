
from typing import Any, Dict, Type, TypeVar
from uuid import UUID
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from promptview.auth.dependencies import get_auth_admin_user, get_auth_user, get_user_manager, verify_api_key
from promptview.auth.user_manager2 import AuthManager, AuthModel, UserNotFound
import os

from promptview.model.model import Model




AUTH_MODEL = TypeVar('AUTH_MODEL', bound=AuthModel)



def create_auth_router(user_manager: AuthManager[AUTH_MODEL]):

    router = APIRouter(
        prefix="/auth",
        tags=["manager"],
        # dependencies=[Depends(get_current_user), ]
    )

    @router.post("/guest", response_model=user_manager.user_model)
    async def create_guest_user(data: Dict[str, Any]):
        """
        Create a guest user. Returns user with guest_token.
        """
        user = await user_manager.create_guest(data)
        return user

    @router.post("/register", response_model=user_manager.user_model)
    async def register_user(data: Dict[str, Any]):
        """
        Register a new user (not via promotion).
        """
        auth_user_id = data.get("auth_user_id")
        if not auth_user_id:
            raise HTTPException(400, detail="auth_user_id required")
        existing_user = await user_manager.fetch_by_auth_user_id(auth_user_id)
        if existing_user:
            raise HTTPException(400, detail="User already exists")
        user = await user_manager.register_user(auth_user_id, data.get("data", {}))
        return user

    @router.post("/promote", response_model=user_manager.user_model)
    async def promote_guest_user(data: Dict[str, Any]):
        """
        Promote guest to registered user. Provide 'guest_token' and 'auth_user_id'.
        """
        guest_token = data.get("guest_token")
        auth_user_id = data.get("auth_user_id")
        if not guest_token:
            raise HTTPException(400, detail="guest_token required")
        if not auth_user_id:
            raise HTTPException(400, detail="auth_user_id required")
        guest = await user_manager.fetch_by_guest_token(guest_token)
        if not guest:
            raise HTTPException(404, detail="Guest not found")
        if not guest.is_guest:
            raise HTTPException(400, detail="User is already registered")
        user = await user_manager.promote_guest(guest, auth_user_id, data.get("data", {}))
        return user

    @router.get("/me", response_model=user_manager.user_model)
    # async def get_me(user: user_manager.user_model = Depends(user_manager.get_user_from_request)):
    async def get_me(request: Request):
        """
        Fetch the current user (guest or registered) using cookie or header.
        """
        try:
            user = await user_manager.get_user_from_request(request)
        except UserNotFound:
            raise HTTPException(401, detail="Unauthorized")
        return user
    
    @router.get("/verify_guest_token")
    async def verify_guest_token(token: str = Query(..., description="The guest token to verify")):
        """
        Verify a guest token.
        """
        user = await user_manager.fetch_by_guest_token(token)
        if not user:
            return {"valid": False}
        return {"valid": True}
    
    
    # @router.get("/me", response_model=user_manager.user_model)
    # async def get_me(request: Request):
    #     """
    #     Fetch the current user (guest or registered) using cookie or header.
    #     """
    #     body = await request.json()
    #     print(body)
    #     user = await user_manager.fetch_by_auth_user_id(body.get("auth_user_id"))
    #     return user


    return router
