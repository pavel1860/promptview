from typing import Generic, List, Optional, Type
from datetime import datetime
from typing_extensions import TypeVar

from promptview.model2.versioning import ArtifactLog
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
    id: int = KeyField(primary_key=True)
    name: str | None = ModelField(None)
    email: str = ModelField(...)
    image: str | None = ModelField(None)
    emailVerified: datetime = ModelField(..., db_type="TIMESTAMPTZ")
    is_admin: bool = ModelField(default=False)
    created_at: datetime = ModelField(default_factory=datetime.now)
    
    async def list_partitions(self):
        return await ArtifactLog.list_partitions(self.id)
    
    async def create_partition(self, name: str, users: List["AuthModel"]):
        return await ArtifactLog.create_partition(name, [self.id] + [user.id for user in users])
    
    

class UserAuthPayload(BaseModel):
    name: str | None = None
    email: str
    emailVerified: datetime
    image: str | None = None
    
    
    
class UserManagerError(Exception):
    pass


AUTH_MODEL = TypeVar("AUTH_MODEL", bound=AuthModel)

class AuthManager(Generic[AUTH_MODEL]):
    
    _auth_model: Optional[Type[AUTH_MODEL]] = None
    
    @classmethod
    def get_user_model(cls) -> Type[AUTH_MODEL]:
        if cls._auth_model is None:
            raise ValueError("User model not registered")
        return cls._auth_model
    
    @classmethod
    def register_user_model(cls, user_model: Type[AUTH_MODEL]):
        cls._auth_model = user_model
    
    @staticmethod
    async def initialize_tables():
#         await PGConnectionManager.execute(
#             """
# CREATE TABLE IF NOT EXISTS verification_token (
#     identifier TEXT NOT NULL,
#     expires TIMESTAMPTZ NOT NULL,
#     token TEXT NOT NULL,
    
#     PRIMARY KEY (identifier, token)
# );

# CREATE TABLE IF NOT EXISTS accounts (
#     id SERIAL,
#     "userId" INTEGER NOT NULL,
#     type VARCHAR(255) NOT NULL,
#     provider VARCHAR(255) NOT NULL,
#     "providerAccountId" VARCHAR(255) NOT NULL,
#     refresh_token TEXT,
#     access_token TEXT,
#     expires_at BIGINT,
#     id_token TEXT,
#     scope TEXT,
#     session_state TEXT,
#     token_type TEXT,
    
#     PRIMARY KEY (id)
# );

# CREATE TABLE IF NOT EXISTS sessions (
#     id SERIAL,
#     "userId" INTEGER NOT NULL,
#     expires TIMESTAMPTZ NOT NULL,
#     "sessionToken" VARCHAR(255) NOT NULL,
    
#     PRIMARY KEY (id)
# );

# CREATE TABLE IF NOT EXISTS users (
#     id SERIAL,
#     name VARCHAR(255),
#     email VARCHAR(255),
#     "emailVerified" TIMESTAMPTZ,
#     image TEXT,
    
#     PRIMARY KEY (id),
    
#     phone_number VARCHAR(255),
#     head_id INTEGER,
#     FOREIGN KEY (head_id) REFERENCES heads(id)
    
# );                                                     
# """)

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
        
        
# CREATE TABLE IF NOT EXISTS users (
#     id SERIAL,
#     name VARCHAR(255),
#     email VARCHAR(255),
#     "emailVerified" TIMESTAMPTZ,
#     image TEXT,
    
#     PRIMARY KEY (id),
    
#     phone_number VARCHAR(255),
#     head_id INTEGER,
#     FOREIGN KEY (head_id) REFERENCES heads(id)
    
# );
        
        
    async def drop_tables(self):
        await PGConnectionManager.execute(
            """
            DROP TABLE IF EXISTS verification_token;
            DROP TABLE IF EXISTS accounts;
            DROP TABLE IF EXISTS sessions;
            DROP TABLE IF EXISTS users;
        """
        )
    
    
    async def create_user(self, data: UserAuthPayload):
        user_model = self.get_user_model()
        user = await user_model(**data.model_dump()).save()
        return user
    
    @classmethod
    async def create_head_for_user(self, user_id: int):
        artifact_log = ArtifactLog()
        head = await artifact_log.create_head()
        await PGConnectionManager.execute(
            f"""
            UPDATE users SET head_id = {head["id"]} WHERE id = {user_id}
            """,
        )
        return head
    
    
    async def get_user(self, id: int):
        user_model = self.get_user_model()
        user = await user_model.get(id)
        return user
    
    
    async def get_user_by_email(self, email: str):
        user_model = self.get_user_model()
        user = await user_model.query().filter(lambda x: x.email == email).first()
        return user
    
    async def get_user_by_session_token(self, session_token: str):
        res = await PGConnectionManager.fetch_one(
            f"""
            SELECT "userId" FROM sessions WHERE "sessionToken" = '{session_token}'
            """
        )
        if res is None:
            raise UserManagerError("Invalid session token")
        return await self.get_user(res["userId"])
    
    
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
    
    
    
    




