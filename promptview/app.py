
from contextlib import asynccontextmanager
from functools import wraps
from typing import Annotated, Any, Awaitable, Callable, Concatenate, Dict, Generic, List, Literal, ParamSpec, Type, TypeVar
from fastapi import Depends, FastAPI, Form, Header


from promptview.api.tracing_router import router as tracing_router
from promptview.api.model_router import create_crud_router
from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthManager, AuthModel
from promptview.model2.context import UserContext
from promptview.testing.test_manager import TestManager
from promptview.model2 import Model, NamespaceManager, Context
from promptview.api.auth_router import create_auth_router
from promptview.api.model_router import create_crud_router
from promptview.api.artifact_log_api import router as artifact_log_router
from promptview.api.testing_router import connect_testing_routers
from promptview.api.user_router import connect_user_model_routers


MSG_MODEL = TypeVar('MSG_MODEL', bound=Model)
USER_MODEL = TypeVar('USER_MODEL', bound=AuthModel)
CTX_MODEL = TypeVar('CTX_MODEL', bound=Context)

P = ParamSpec('P')

EnpointType = Callable[Concatenate[CTX_MODEL, MSG_MODEL, P], Awaitable[List[MSG_MODEL]]]

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
            ns = user_model.get_namespace()
            await AuthManager.initialize_tables()
            AuthManager.register_user_model(user_model)
            await NamespaceManager.create_all_namespaces(ns.name)
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
    
    def register_model_api(self, model: Type[Model]):
        self._app.include_router(create_crud_router(model), prefix="/api/model")
    
    def setup_apis(self):
        self._app.include_router(create_crud_router(self._message_model), prefix="/api/model")
        self._app.include_router(artifact_log_router, prefix="/api")
        self._app.include_router(create_auth_router(self._user_model), prefix="/api")
        self._app.include_router(tracing_router, prefix="/api")
        connect_user_model_routers(self._app, [self._user_model])
        connect_testing_routers(self._app)

    
    def entrypoint(self, path: str, method: Literal['GET', 'POST', 'PUT', 'DELETE'] = 'POST', auto_commit: bool = True):
        def decorator(func: EnpointType):
            self._entrypoints_registry[path] = func
            async def input_endpoint(
                message_json:  Annotated[str, Form(...)],
                user_context_json: Annotated[str, Form(...)],
                # head_id: Annotated[int, Header(alias="head_id")],
                user: Any = Depends(get_auth_user),
                branch_id: Annotated[int | None, Header(alias="branch_id")] = None,
            ):
                print(user)
                message = self._message_model.model_validate_json(message_json)
                user_context = UserContext.model_validate_json(user_context_json)
                # async with self._ctx_model(head_id=head_id, branch_id=branch_id) as ctx:                
                async with self._ctx_model(
                    user, 
                    auto_commit=auto_commit, 
                    user_context=user_context
                ).start_turn(branch_id=branch_id) \
                    .start_tracer(
                        name=func.__name__, 
                        run_type="chain", 
                        inputs={
                            "message": message.model_dump_json(),
                            "user_context": user_context.model_dump_json(),
                            "branch_id": branch_id,
                        }
                    ) as ctx:
                    responses = await func(ctx=ctx, message=message)
                    print(ctx.user_context)
                return [message, *responses]
            
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
    
    
    
    
    
    