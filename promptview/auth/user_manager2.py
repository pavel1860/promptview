from typing import Any, Dict, Generic, List, Optional, Type, final
from datetime import datetime
from uuid import UUID, uuid4
from fastapi import HTTPException, Request
from typing_extensions import TypeVar


from pydantic import BaseModel
from promptview.model2 import Model, ModelField
from promptview.model2.fields import KeyField
from promptview.utils.db_connections import PGConnectionManager




from uuid import UUID
from promptview.model2.model import Model


class AuthModel(Model):
    _is_base: bool = True
    id: int = KeyField(primary_key=True)
    auth_user_id: str | None = ModelField(None, index="btree")
    is_guest: bool = ModelField(default=True)
    guest_token: UUID | None = ModelField(None)
    is_admin: bool = ModelField(default=False)
    created_at: datetime = ModelField(default_factory=datetime.now)

    
    
    
class UserNotFound(Exception):
    pass

class UserAlreadyExists(Exception):
    pass


class UserNotAuthorized(Exception):
    pass
    



UserT = TypeVar("UserT", bound=AuthModel)

class AuthManager(Generic[UserT]):
    user_model: Type[UserT]

    def __init__(self, user_model: Type[UserT]):
        self.user_model = user_model

    # --------- Hooks ----------
    async def before_create_guest(self, data: Dict[str, Any]) -> None: pass
    async def after_create_guest(self, user: UserT) -> None: pass
    async def before_register_user(self, data: Dict[str, Any]) -> None: pass
    async def after_register_user(self, user: UserT) -> None: pass
    async def before_promote_guest(self, guest: UserT, data: Dict[str, Any]) -> None: pass
    async def after_promote_guest(self, user: UserT) -> None: pass
    async def before_fetch_user(self, identifier: Any) -> None: pass
    async def after_fetch_user(self, user: Optional[UserT]) -> None: pass

    # --------- Core Logic ----------
    async def create_guest(self, data: Dict[str, Any]) -> UserT:
        await self.before_create_guest(data)
        user = await self.user_model(
            is_guest=True,
            guest_token=str(uuid4()),  # fill in UUID creation
            created_at=datetime.utcnow(),
            **data
        ).save()
        # Save to DB here
        await self.after_create_guest(user)
        return user

    async def register_user(self, auth_user_id: str, data: Dict[str, Any]) -> UserT:
        await self.before_register_user(data)
        if await self.fetch_by_auth_user_id(auth_user_id):
            raise UserAlreadyExists(f"User {auth_user_id} already exists")
        user = await self.user_model(
            is_guest=False,            
            auth_user_id=auth_user_id,
            **data
        ).save()
        # Save to DB here
        await self.after_register_user(user)
        return user

    async def promote_guest(self, guest: UserT, auth_user_id: str, data: Dict[str, Any]) -> UserT:
        await self.before_promote_guest(guest, data)
        user = await self.fetch_by_auth_user_id(auth_user_id)
        if user:
            raise HTTPException(400, detail="User already exists")
        guest = await guest.update(
            **data, 
            is_guest=False, 
            guest_token=None,
            auth_user_id=auth_user_id
        )
        # Update in DB
        await self.after_promote_guest(guest)
        return guest

    # --------- Fetch Logic with Dependency Pattern ----------
    async def fetch_by_auth_user_id(self, identifier: Any) -> Optional[UserT]:
        await self.before_fetch_user(identifier)
        user = await self.user_model.query().where(auth_user_id=identifier).last()
        await self.after_fetch_user(user)
        return user
    
    
    async def fetch_by_guest_token(self, identifier: Any) -> Optional[UserT]:
        await self.before_fetch_user(identifier)
        user = await self.user_model.query().where(guest_token=identifier).last()
        await self.after_fetch_user(user)
        return user
    
    async def get_user_from_request(self, request: Request) -> Optional[UserT]:
        guest_token = request.cookies.get("temp_user_token")
        auth_user_id = request.headers.get("X-Auth-User")
        user = None
        if auth_user_id:
            user = await self.fetch_by_auth_user_id(auth_user_id)
            if not user:
                raise UserNotFound(f"User {auth_user_id} not found")
        elif guest_token:
            user = await self.fetch_by_guest_token(guest_token)
            if not user:
                raise UserNotFound(f"Guest User {guest_token} not found")
        
        return user

    def get_user(self):
        async def _get_user_dep(request: Request):
            # Try to fetch user from request/session/cookie/etc.
            # Example:
            guest_token = request.cookies.get("temp_user_token")
            auth_user_id = request.headers.get("X-Auth-User")
            user = None
            if auth_user_id:
                user = await self.fetch_by_auth_user_id(auth_user_id)
            elif guest_token:
                user = await self.fetch_by_guest_token(guest_token)
            if not user:
                raise HTTPException(401, detail="User not found")
            return user
        return _get_user_dep