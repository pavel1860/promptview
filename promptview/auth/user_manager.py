from typing import Generic, List, Optional, Type, final
from datetime import datetime
from uuid import UUID, uuid4
from typing_extensions import TypeVar


from pydantic import BaseModel
from promptview.model2 import Model, ModelField
from promptview.model2.fields import KeyField
from promptview.utils.db_connections import PGConnectionManager


# class UserModel(Model, HeadModel):
#     name: str | None = ModelField(None)
#     email: str = ModelField(...)
#     image: str | None = ModelField(None)
#     emailVerified: datetime = ModelField(..., db_type="TIMESTAMPTZ")
#     is_admin: bool = ModelField(default=False)
#     # user_auth_id: int = ModelField(...)
    
#     class Config: # do not fix this!
#         database_type="postgres"
#         is_head=True
#         is_abstract=True
#         namespace="users"

#     async def check_out_head(self, head_id: int):
#         head = await PGConnectionManager.fetch_one(
#             f"""
#             UPDATE heads AS uh
#             SET 
#                 main_branch_id = th.main_branch_id,
#                 branch_id      = th.branch_id,
#                 turn_id        = th.turn_id,
#                 updated_at     = NOW()
#             FROM heads AS th
#             WHERE uh.id = {self.head.id}
#             AND th.id = {head_id}
#             RETURNING uh.*;
#             """
#         )
#         if head is None:
#             raise UserManagerError("Invalid head id")
#         return dict(head)


class AuthModel(Model):
    _is_base: bool = True
    id: int = KeyField(primary_key=True)
    user_token: UUID = ModelField(None)
    name: str | None = ModelField(None)
    email: str | None = ModelField(None)
    image: str | None = ModelField(None)
    emailVerified: datetime | None = ModelField(None, db_type="TIMESTAMPTZ")
    is_admin: bool = ModelField(default=False)
    created_at: datetime = ModelField(default_factory=datetime.now)
    
    
    
    
    

class UserAuthPayload(BaseModel):
    name: str | None = None
    user_token: UUID | None = None
    email: str | None = None
    emailVerified: datetime | None = None
    image: str | None = None
    
    
    
class UserManagerError(Exception):
    pass


AUTH_MODEL = TypeVar("AUTH_MODEL", bound=AuthModel)

class AuthManager(Generic[AUTH_MODEL]):
    
    _auth_model: Optional[Type[AUTH_MODEL]] = None
    _add_temp_users: bool = False
    
    @classmethod
    def get_user_model(cls) -> Type[AUTH_MODEL]:
        if cls._auth_model is None:
            raise ValueError("User model not registered")
        return cls._auth_model
    
    @classmethod
    def register_user_model(cls, user_model: Type[AUTH_MODEL], add_temp_users: bool = False):
        cls._auth_model = user_model
        cls._add_temp_users = add_temp_users
    
    @staticmethod
    async def initialize_tables():

        await PGConnectionManager.execute(
            """
CREATE TABLE IF NOT EXISTS verification_token (
    identifier TEXT NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    token TEXT NOT NULL,
    
    PRIMARY KEY (identifier, token)
);

CREATE TABLE IF NOT EXISTS accounts (
    id SERIAL,
    "userId" INTEGER NOT NULL,
    type VARCHAR(255) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    "providerAccountId" VARCHAR(255) NOT NULL,
    refresh_token TEXT,
    access_token TEXT,
    expires_at BIGINT,
    id_token TEXT,
    scope TEXT,
    session_state TEXT,
    token_type TEXT,
    
    PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL,
    "userId" INTEGER NOT NULL,
    expires TIMESTAMPTZ NOT NULL,
    "sessionToken" VARCHAR(255) NOT NULL,
    
    PRIMARY KEY (id)
);                                                     
""")
        
        
 
        
    async def drop_tables(self):
        await PGConnectionManager.execute(
            """
            DROP TABLE IF EXISTS verification_token;
            DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS users;
        """
        )
        
    
    async def after_create_user(self, user: AUTH_MODEL):
        return user
    
    async def before_create_user(self, data: UserAuthPayload) -> UserAuthPayload:
        return data
    
    
    @final
    async def create_user(self, data: UserAuthPayload):
        data = await self.before_create_user(data)
        user_model = self.get_user_model()
        user = await user_model(**data.model_dump()).save()
        user = await self.after_create_user(user)
        return user
    
    # @classmethod
    # async def create_head_for_user(self, user_id: int):
    #     artifact_log = ArtifactLog()
    #     head = await artifact_log.create_head()
    #     await PGConnectionManager.execute(
    #         f"""
    #         UPDATE users SET head_id = {head["id"]} WHERE id = {user_id}
    #         """,
    #     )
    #     return head
    
    
    async def get_user(self, id: int):
        user_model = self.get_user_model()
        user = await user_model.get(id)
        return user
    
    
    async def get_user_by_email(self, email: str):
        user_model = self.get_user_model()
        user = await user_model.query().filter(lambda x: x.email == email).first()
        return user
    
    
    async def get_user_by_session_token(self, session_token: str, use_sessions: bool = True):
        if use_sessions:
            res = await PGConnectionManager.fetch_one(
                f"""
                SELECT "userId" FROM sessions WHERE "sessionToken" = '{session_token}'
                """
            )
            if res is None:
                raise UserManagerError("Invalid session token")
            return await self.get_user(res["userId"])
        else:
            res = await PGConnectionManager.fetch_one(
                f"""
                SELECT "id" FROM users WHERE user_token = '{session_token}'
                """
            )
            if res is None:
                return None
            return await self.get_user(res["id"])
        
    
    
    async def change_head(self, user_id: int, head_id: int):
        head = await PGConnectionManager.fetch_one(
            f"""
            WITH taget_head AS (
                SELECT * FROM heads WHERE id = {head_id}
            ), user_head AS (
                SELECT uh.* FROM heads uh
                JOIN users u ON u.head_id = uh.id
                WHERE u.id = {user_id}
            )
            UPDATE heads SET head_id = (SELECT id FROM head) WHERE id = {user_id}
            """
        )
        if head is None:
            raise UserManagerError("Invalid head id")        
    
    async def update_user(self):
        pass
    
    async def delete_user(self):
        pass
    

    
    async def get_users(self):
        user_model = self.get_user_model()
        users = await user_model.query().filter(lambda x: x.is_admin == False)
        return users
    
    
    
    




