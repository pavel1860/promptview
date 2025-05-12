

from typing import Type, TypeVar
from fastapi import Request,  Depends, HTTPException, Query, Request
import json


from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthModel
from promptview.context.model_context import ModelCtx
from promptview.model2.versioning import ArtifactLog, Partition
from pydantic import BaseModel
from promptview.model2.query_filters import QueryFilter, parse_query_params




class Head(BaseModel):
    partition_id: int | None = None
    branch_id: int = 1
    turn_id: int | None = None
    partition: Partition | None = None


def unpack_int_env_header(request: Request, field: str, default: int | None = None):
    value = request.headers.get(field)
    if value is None or value == "null":
        return default
    return int(value)


def query_filters(request: Request) -> QueryFilter | None:
    filters = request.query_params.get("filter")
    if filters:
        return parse_query_params(json.loads(filters))
    return None


def build_head_parser(model: Type[BaseModel]):
    async def get_head(request: Request, auth_user: AuthModel = Depends(get_auth_user)) -> Head | None:
        partition_id = unpack_int_env_header(request, "partition_id")
        if partition_id is None:
            if not auth_user.is_admin:
                raise HTTPException(status_code=401, detail="Unauthorized")
        if partition_id != auth_user.id:
            if not auth_user.is_admin:
                raise HTTPException(status_code=401, detail="Unauthorized")
        if not model._is_versioned:
            return None
        branch_id = unpack_int_env_header(request, "branch_id")
        if branch_id is None:
            branch_id = 1
        turn_id = unpack_int_env_header(request, "turn_id")
        head = Head(branch_id=branch_id, turn_id=turn_id)
        return head
    return get_head



async def get_head(request: Request, auth_user: AuthModel = Depends(get_auth_user)) -> Head | None:
    partition_id = unpack_int_env_header(request, "partition_id")
    partition = None
    if partition_id is None:
        if not auth_user.is_admin:
            partition = await auth_user.last_partition("default")
            if not partition:
                raise HTTPException(status_code=401, detail="No Partition specified for regular user")        
    else:
        partition = await ArtifactLog.get_partition(partition_id)
        if not partition.is_participant(auth_user.id) and not auth_user.is_admin:
            raise HTTPException(status_code=401, detail="Unauthorized partition for user")
        
    branch_id = unpack_int_env_header(request, "branch_id")
    if branch_id is None:
        branch_id = 1
    turn_id = unpack_int_env_header(request, "turn_id")
    head = Head(branch_id=branch_id, turn_id=turn_id, partition_id=partition_id, partition=partition)
    return head
    
    

MODEL_CONTEXT = TypeVar("MODEL_CONTEXT", bound=BaseModel)


def build_model_context_parser(model_context_cls: Type[MODEL_CONTEXT]):
    def extract_model_context(request: Request) -> MODEL_CONTEXT:
        raw = {}
        for key in request.headers.keys():
            if key.endswith("_id"):
                val = request.headers.get(key)
                if val and val != "null":
                    raw[key] = int(val) if val.isdigit() else val
        return model_context_cls(**raw)
    return extract_model_context



