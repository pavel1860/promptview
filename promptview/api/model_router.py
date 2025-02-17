from typing import Dict, Type, List, TypeVar, Generic
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.datastructures import QueryParams
from pydantic import BaseModel

# from app.util.dependencies import get_partitions
from promptview.model.resource_manager import connection_manager
# from app.util.auth import varify_token
# from app.util.dependencies import unpack_request_token
from promptview.model.model import Model
from typing import Type, Any, Dict, Optional
from fastapi import Query
from pydantic import BaseModel
from promptview.artifact_log.artifact_log3 import ArtifactLog

MODEL = TypeVar("MODEL", bound=Model)




def create_crud_router(model: Type[MODEL]) -> APIRouter:
    # router = APIRouter(prefix=f"/{model.__name__.lower()}", tags=[model.__name__.lower()])
    router = APIRouter(prefix=f"/{model.__name__}", tags=[model.__name__.lower()])
    
    # class ModelQuery(model):
    #     limit: int = 10
    #     offset: int = 0
    
    # async def get_partitions(request: Request, token: str = Depends(unpack_request_token)):
    #     payload = varify_token(token)
    #     query_keys = [p for p in request.query_params if p not in ['limit', 'offset']]
    #     bad_keys = [p for p in query_keys if p not in model.model_fields]
    #     if bad_keys:
    #         raise HTTPException(status_code=400, detail=f"Invalid query parameters: {bad_keys}")
    #     if 'manager_phone_number' in query_keys:
    #         if request.query_params.get('manager_phone_number') != payload.user_phone:
    #             raise HTTPException(status_code=403, detail="Forbidden")
    #     partitions = {k: request.query_params[k] for k in query_keys}
    #     partitions.update({"manager_phone_number": payload.user_phone})
    #     return partitions
    
    
    async def env_ctx(request: Request):
        head_id = request.headers.get("head_id")
        branch_id = request.headers.get("branch_id")
        # with connection_manager.set_env(env or "default"):
            # yield env
        if head_id is None:
            raise HTTPException(status_code=400, detail="head_id is not supported")
        async with ArtifactLog(head_id=int(head_id), branch_id=int(branch_id)) as art_log:
            yield art_log
    
    def validate_access(instance: MODEL, partitions: Dict[str, str]):
        for key, value in partitions.items():
            if getattr(instance, key) != value:
                raise HTTPException(status_code=403, detail="Forbidden")
        return instance
    
    
    def generate_filter_args(model: Type[BaseModel]) -> Dict[str, Any]:
        """
        Dynamically generate query parameters for filtering based on model fields.
        """
        filters = {}
        for field_name, field_type in model.__annotations__.items():
            filters[field_name] = Query(
                None, description=f"Filter by {field_name}", alias=field_name
            )
        return filters


    def filter_dependency(model: Type[BaseModel]) -> Any:
        """
        Dependency to extract and return filter arguments.
        """
        def filter_query(**filters: Any):
            return {key: value for key, value in filters.items() if value is not None}

        def dependency():
            return filter_query(**generate_filter_args(model))

        return Depends(dependency)



    @router.post("/create", response_model=model)
    async def create_instance(data: dict, env: str = Depends(env_ctx)):
        instance = model(**data)
        await instance.save()  # Assuming your save method is asynchronous
        return instance

    @router.get("/id/{item_id}", response_model=model)
    async def read_instance(item_id: str, env: str = Depends(env_ctx)):
        instance = await model.get(item_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Item not found")            
        return instance

    @router.post("/update/{item_id}", response_model=model)
    async def update_instance(item_id: str, updates: dict, env: str = Depends(env_ctx)):
        instance = await model.get(item_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Item not found")
        for key, value in updates.items():
            setattr(instance, key, value)
        await instance.save()
        return instance

    @router.post("/delete/{item_id}")
    async def delete_instance(item_id: str, env: str = Depends(env_ctx)):
        instance = await model.get(item_id)
        if not instance:
            raise HTTPException(status_code=404, detail="Item not found")
        result = await model.delete(item_id)
        if not result:
            raise HTTPException(status_code=404, detail="Item not found")
        return {"detail": "Item deleted"}

    @router.get("/list", response_model=List[model])
    async def list_instances(
            limit: int = 10, 
            offset: int = 0, 
            # filters: Dict[str, Any] = Depends(filter_dependency(model)), 
            # partitions: dict = Depends(get_partitions),
            env: str = Depends(env_ctx)
        ):
        model_query = model.limit(limit).offset(offset)
        # model_query._filters = filters
        instances = await model_query        
        return instances
    
    @router.get("/last", response_model=model | None)
    async def last_instance(request: Request, env: str = Depends(env_ctx)):
        query_params = dict(request.query_params)
        instance = await model.last(query_params)
        if not instance:
            return None
        return instance
    
    @router.get("/first", response_model=model | None)
    async def first_instance(request: Request, env: str = Depends(env_ctx)):
        query_params = dict(request.query_params)
        instance = await model.first(query_params)
        if not instance:
            return None
        return instance
    
    # @router.get("/similar", response_model=List[model])
    # async def similar_instances(query: str, limit: int = 10, offset: int = 0, partitions: dict = Depends(get_partitions)):
    #     return await model.similar()

    return router




model_manager_router = APIRouter(prefix=f"/manager", tags=["manager"])

@model_manager_router.get("/envs")
async def get_envs():    
    return connection_manager.get_env_names()

def connect_model_routers(app, model_list: List[Type[Model]], envs: Dict[str, Dict[str, str]] | None = None):
    for model in model_list:
        router = create_crud_router(model)
        app.include_router(router, prefix=f"/model", tags=[model.__name__.lower()])
    if envs:
        for env_name, env in envs.items():
            connection_manager.add_env(env_name, env)
    app.include_router(model_manager_router, prefix="/model", tags=["manager"])
    
    