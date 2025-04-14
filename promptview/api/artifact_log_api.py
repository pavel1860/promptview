from typing import Dict, Type, List, TypeVar, Generic
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.datastructures import QueryParams
from promptview.api.utils import Head, build_head_parser, get_head
from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthModel
from pydantic import BaseModel
from promptview.model2.versioning import ArtifactLog, Branch, Partition, Turn, TurnStatus




router = APIRouter(prefix="/artifact_log", tags=["artifact_log"])


# def unpack_int_env_header(request: Request, field: str):    
#     value = request.headers.get(field)
#     if value is None or value == "null" or value == "undefined":
#         return None
#     return int(value)


# def get_artifact_log(request: Request):
#     head_id = unpack_int_env_header(request, "head_id")
#     branch_id = unpack_int_env_header(request, "branch_id")
#     if head_id is None:
#         raise HTTPException(status_code=400, detail="head_id is not supported")
#     try:
#         return ArtifactLog(head_id=head_id, branch_id=branch_id)
#     except Exception as e:
#         raise HTTPException(status_code=400, detail=str(e))




@router.get("/branches", response_model=List[Branch])
async def get_branches():
    branches = await ArtifactLog.list_branches()
    return branches


@router.get("/branches/{branch_id}", response_model=Branch)
async def get_branch(branch_id: int):
    branch = await ArtifactLog.get_branch(branch_id)
    return branch



class BranchFromTurnRequest(BaseModel):
    turn_id: int
    
@router.post("/branches")
async def branch_from_turn(request: BranchFromTurnRequest, head: Head = Depends(get_head)):
    branch = await ArtifactLog.create_branch(forked_from_turn_id=request.turn_id)
    return branch


@router.get("/all_turns", response_model=List[Turn])
async def get_all_turns():
    turns = await ArtifactLog.list_turns()
    return turns


@router.get("/partitions", response_model=List[Partition])
async def get_partitions(user: AuthModel = Depends(get_auth_user)):
    partitions = await ArtifactLog.list_partitions(user.id)
    return partitions


class CreatePartitionPayload(BaseModel):
    name: str
    participants: List[int]

@router.post("/partitions")
async def create_partition(payload: CreatePartitionPayload, user: AuthModel = Depends(get_auth_user)):
    partition = await ArtifactLog.create_partition(payload.name, [user.id] + payload.participants)
    return partition

# @router.get("/heads/{head_id}")
# async def get_head(head_id: int):
#     raise NotImplementedError

    
    
@router.get("/turns/{branch_id}", response_model=List[Turn])
async def get_branch_turns(branch_id: int):    
    turns = await ArtifactLog.get_branch_turns(branch_id)
    return turns



@router.post("/turns/update/{turn_id}")
async def update_turn(turn_id: int, request: Request):
    body = await request.json()    
    turn = await ArtifactLog.update_turn(turn_id, **body)
    return turn

@router.get("/heads")
async def get_head_list():    
    raise NotImplementedError

