

from typing import Type, Depends, HTTPException, Query, Request
from fastapi import Request
import json

from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthModel
from promptview.prompt.depends import Depends
from pydantic import BaseModel
from promptview.model2.query_filters import QueryFilter, parse_query_params




class Head(BaseModel):
    partition_id: str | None = None
    branch_id: int = 1
    turn_id: int | None = None


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
        if partition_id is None:
            if not auth_user.is_admin:
                raise HTTPException(status_code=401, detail="Unauthorized")
        if partition_id != auth_user.id:
            if not auth_user.is_admin:
                raise HTTPException(status_code=401, detail="Unauthorized")
        branch_id = unpack_int_env_header(request, "branch_id")
        if branch_id is None:
            branch_id = 1
        turn_id = unpack_int_env_header(request, "turn_id")
        head = Head(branch_id=branch_id, turn_id=turn_id)
        return head