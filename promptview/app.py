
from contextlib import asynccontextmanager
from functools import wraps
from typing import Annotated, Any, Awaitable, Callable, Concatenate, Dict, Generic, Literal, ParamSpec, Type, TypeVar
from fastapi import FastAPI, Form, Header

from promptview import testing
from promptview.api.model_router import create_crud_router
from promptview.artifact_log.artifact_log3 import ArtifactLog
from promptview.auth.user_manager import UserManager, UserModel
from promptview.testing.test_manager import TestManager
from promptview.model.model import Model
from promptview.model.resource_manager import connection_manager
from promptview.prompt.context import Context
from promptview.api.auth_router import router as auth_router
from promptview.api.model_router import create_crud_router
from promptview.api.head_model_router import create_head_crud_router
from promptview.api.artifact_log_api import router as artifact_log_router
from promptview.api.testing_router import connect_testing_routers
from promptview.api.user_router import connect_user_model_routers


MSG_MODEL = TypeVar('MSG_MODEL', bound=Model)
USER_MODEL = TypeVar('USER_MODEL', bound=UserModel)
CTX_MODEL = TypeVar('CTX_MODEL', bound=Context)

P = ParamSpec('P')

EnpointType = Callable[Concatenate[CTX_MODEL, MSG_MODEL, P], Awaitable[MSG_MODEL]]

class Chatboard(Generic[MSG_MODEL, USER_MODEL, CTX_MODEL]):
    _app: FastAPI
    _entrypoints_registry: Dict[str, EnpointType]
    _message_model: Type[MSG_MODEL]
    _user_model: Type[USER_MODEL]
    _ctx_model: Type[CTX_MODEL]
    
    def __init__(
        self, 
        message_model: Type[MSG_MODEL], 
        user_model: Type[USER_MODEL], 
        ctx_model: Type[CTX_MODEL],
        app: FastAPI | None = None
    ):
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # This code runs before the server starts serving
            artifact_log = ArtifactLog()
            await artifact_log.initialize_tables()
            UserManager.register_user_model(user_model)
            await UserManager.initialize_tables() 
            await connection_manager.init_all_namespaces()            
            # Yield to hand control back to FastAPI (start serving)
            yield
            
        self._app = app or FastAPI(lifespan=lifespan)
        self._entrypoints_registry = {}
        self._message_model = message_model
        self._user_model = user_model
        self._ctx_model = ctx_model
        
        self.setup_apis()
        
    def get_app(self):
        return self._app
    
    def setup_apis(self):
        self._app.include_router(create_crud_router(self._message_model), prefix="/api/model")
        self._app.include_router(artifact_log_router, prefix="/api")
        self._app.include_router(auth_router, prefix="/api")
        connect_user_model_routers(self._app, [self._user_model])
        connect_testing_routers(self._app)

    
    def entrypoint(self, path: str, method: Literal['GET', 'POST', 'PUT', 'DELETE'] = 'POST', auto_commit: bool = True):
        def decorator(func: EnpointType):
            self._entrypoints_registry[path] = func
            async def input_endpoint(
                message_json:  Annotated[str, Form(...)],
                head_id: Annotated[int, Header(alias="head_id")],
                branch_id: Annotated[int | None, Header(alias="branch_id")] = None,
            ):
                message = self._message_model.model_validate_json(message_json)
                with self._ctx_model(head_id=head_id, branch_id=branch_id) as ctx:
                    response = await func(ctx=ctx, message=message)
                    if auto_commit:
                        await ctx.commit()
                return [response, message]
            
            async def test_endpoint(
                body: dict,
            ):
                test_case_id = body.get("test_case_id")
                async with TestManager(test_case_id=test_case_id) as tm:
                        for inputs, evaluator in tm.iter_turns():
                            async with self._ctx_model(head_id=tm.head_id) as ctx:
                                message = self._message_model(content=inputs, role="user")
                                response = await func(ctx=ctx, message=message)
                                await ctx.commit()
                            await evaluator(response.content)
                return tm.test_run
            
            self._app.add_api_route(path, endpoint=input_endpoint, methods=[method])
            self._app.add_api_route("/api/testing/run", endpoint=test_endpoint, methods=["POST"])
            
            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)
            return wrapper
        return decorator
    
    
    
    
    
    