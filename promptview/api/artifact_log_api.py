from typing import Dict, Type, List, TypeVar, Generic
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.datastructures import QueryParams

from promptview.artifact_log.artifact_log3 import ArtifactLog, Branch







router = APIRouter(prefix="/artifact_log", tags=["artifact_log"])


def get_artifact_log(request: Request):
    head_id = request.headers.get("head_id")
    branch_id = request.headers.get("branch_id")
    if head_id is None:
        raise HTTPException(status_code=400, detail="head_id is not supported")
    return ArtifactLog(head_id=int(head_id), branch_id=int(branch_id) if branch_id is not None else None)

@router.get("/branches", response_model=List[Branch])
async def get_branches(artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        branches = await artifact_log.get_branch_list()
        return branches


@router.get("/branches/{branch_id}", response_model=Branch)
async def get_branch(branch_id: int, artifact_log: ArtifactLog = Depends(get_artifact_log)):
    async with artifact_log:
        branch = await artifact_log.get_branch(branch_id)
        return branch




