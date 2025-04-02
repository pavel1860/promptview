import json
from typing import Type, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from promptview.model.query import parse_query_params
from promptview.model2.model import ArtifactModel
from promptview.model2.query_filters import QueryFilter, QueryListType
from promptview.api.utils import query_filters, unpack_int_env_header, Head


def create_artifact_router(model: Type[ArtifactModel]):
    
    router = APIRouter(prefix=f"/{model.__name__}", tags=[model.__name__.lower()])
    
    
    
    async def get_head(request: Request) -> Head | None:
        if not model._is_versioned:
            return None
        branch_id = unpack_int_env_header(request, "branch_id")
        if branch_id is None:
            branch_id = 1
        turn_id = unpack_int_env_header(request, "turn_id")
        head = Head(branch_id=branch_id, turn_id=turn_id)
        return head
    
    @router.get("/list", response_model=List[dict])
    async def list_artifacts(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
        filters: QueryListType | None = Depends(query_filters), 
        head: Head | None = Depends(get_head)
    ):
        """List all artifacts with pagination"""
        
        if head is None:
            query = model.query()
        else:
            query = model.query(branch=head.branch_id)
                
        model_query = query.limit(limit).offset(offset).order_by("created_at", "desc")
        if filters:
            model_query = model_query.set_filter(filters)
        # model_query._filters = filters
        instances = await model_query 
        return [instance.model_dump() for instance in instances]       
    
    @router.get("/{artifact_id}")
    async def get_artifact(artifact_id: UUID):
        """Get a specific artifact by ID"""
        artifact = await model.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact
    
    
    @router.get("/{artifact_id}/version/{version}")
    async def get_artifact_version(artifact_id: UUID, version: int):
        """Get a specific artifact by ID and version"""
        artifact = await model.get_artifact(artifact_id, version)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    
    @router.post("/")
    async def create_artifact(artifact: model):
        """Create a new artifact"""
        try:
            created_artifact = await artifact.save()
            return created_artifact
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.put("/{artifact_id}")
    async def update_artifact(artifact_id: UUID, updated_artifact: model):
        """Update an existing artifact"""
        existing = await model.query().filter(lambda x: x.id == artifact_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        try:
            for field, value in updated_artifact.dict(exclude_unset=True).items():
                setattr(existing, field, value)
            updated = await existing.save()
            return updated
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.delete("/{artifact_id}")
    async def delete_artifact(artifact_id: UUID):
        """Delete an artifact"""
        existing = await model.query().filter(lambda x: x.id == artifact_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        try:
            await existing.delete()
            return {"message": "Artifact deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.get("/last")
    async def last_artifact(
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100)
    ):
        """Get the last artifact with pagination"""
        artifact = await model.query().last()
        return artifact
    
    @router.get("/first")
    async def first_artifact(
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100)
    ):
        """Get the first artifact with pagination"""
        artifact = await model.query().first()
        return artifact
    
    
    return router
    
    
    
    
    
    
    