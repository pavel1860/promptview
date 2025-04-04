
from fastapi import Request
import json

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