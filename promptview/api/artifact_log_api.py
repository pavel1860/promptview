from typing import Dict, Type, List, TypeVar, Generic
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.datastructures import QueryParams
from pydantic import BaseModel

from promptview.artifact_log.artifact_log3 import ArtifactLog, Branch, Head, Turn







router = APIRouter(prefix="/artifact_log", tags=["artifact_log"])


def unpack_int_env_header(request: Request, field: str):    
    value = request.headers.get(field)
    if value is None or value == "null" or value == "undefined":
        return None
    return int(value)


def get_artifact_log(request: Request):
    head_id = unpack_int_env_header(request, "head_id")
    branch_id = unpack_int_env_header(request, "branch_id")
    if head_id is None:
        raise HTTPException(status_code=400, detail="head_id is not supported")
    try:
        return ArtifactLog(head_id=head_id, branch_id=branch_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/branches", response_model=List[Branch])
async def get_branches(artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        branches = await artifact_log.get_branch_list(order_direction="ASC")
        return branches


@router.get("/branches/{branch_id}", response_model=Branch)
async def get_branch(branch_id: int, artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        branch, last_turn, selected_turn, is_detached = await artifact_log.get_branch(branch_id)
        return branch



class BranchFromTurnRequest(BaseModel):
    turn_id: int
    
@router.post("/branches")
async def branch_from_turn(request: BranchFromTurnRequest, artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        branch = await artifact_log.branch_from(request.turn_id, check_out=True)
        return branch


@router.get("/all_turns", response_model=List[Turn])
async def get_all_turns(artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        turns = await artifact_log.get_all_turns()
        return turns

@router.get("/heads/{head_id}", response_model=Head)
async def get_head(head_id: int, artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        head = artifact_log.head
        return Head(**dict(head))

    
    
@router.get("/turns/{branch_id}", response_model=List[Turn])
async def get_branch_turns(branch_id: int, artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        turns = await artifact_log.get_branch_turns(branch_id)
        return turns



@router.get("/heads", response_model=List[Head])
async def get_head_list():    
    heads = await ArtifactLog.get_head_list()
    return heads

