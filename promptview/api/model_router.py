import json
from typing import Type, List, Optional, TypeVar
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthModel
from promptview.model.query import parse_query_params
from promptview.context.model_context import CtxRequest, ModelCtx
from promptview.model2.query_filters import QueryFilter, QueryListType
from promptview.api.utils import build_model_context_parser, get_head, query_filters, unpack_int_env_header, Head
from promptview.model2.model import Model
from promptview.model2 import Context

MODEL = TypeVar("MODEL", bound=Model)
CTX_MODEL = TypeVar("CTX_MODEL", bound=Context)

def create_model_router(model: Type[MODEL], model_context_cls: Type[CTX_MODEL]):
    
    # model_context_parser = build_model_context_parser(model_context_cls)
    async def model_context_parser(request: Request, ctx: Context = Depends(model_context_cls.from_request)):
        ctx._request = CtxRequest(request=request)
        return ctx
    
    router = APIRouter(prefix=f"/{model.__name__}", tags=[model.__name__.lower()])
    
    @router.get("/list", response_model=List[dict])
    async def list_models(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
        filters: QueryListType | None = Depends(query_filters),         
        ctx: CTX_MODEL = Depends(model_context_parser)
    ):
        """List all models with pagination"""
        async with ctx:        
            query = model.query()
                    
            model_query = query.limit(limit).offset(offset).order_by("-created_at")
            if filters:
                model_query = model_query.set_filter(filters)
            # model_query._filters = filters
            instances = await model_query
            return [instance.model_dump() for instance in instances]       
    
    @router.get("/{artifact_id}")
    async def get_artifact(ctx: CTX_MODEL):
        """Get a specific artifact by ID"""
        artifact = await model.get_artifact(ctx.artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact
    
    
    # @router.get("/{artifact_id}/version/{version}")
    # async def get_artifact_version(artifact_id: UUID, version: int):
    #     """Get a specific artifact by ID and version"""
    #     artifact = await model.get_artifact(artifact_id, version)
    #     if not artifact:
    #         raise HTTPException(status_code=404, detail="Artifact not found")
    #     return artifact

    
    @router.post("/create")
    async def create_model(
        payload: dict = Body(...),
        ctx: CTX_MODEL = Depends(model_context_parser)
    ):
        """Create a new model"""
        try:
            async with ctx:
                model_payload = model(**payload)
                created_model = await model_payload.save()
                return created_model
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.put("/update")
    async def update_model(model: MODEL, ctx: CTX_MODEL = Depends(model_context_parser)):
        """Update an existing model"""
        existing = await model.query().filter(lambda x: x.id == model.id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Model not found")
        
        try:
            for field, value in model.dict(exclude_unset=True).items():
                setattr(existing, field, value)
            updated = await existing.save()
            return updated
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.delete("/delete")
    async def delete_model(ctx: CTX_MODEL):
        """Delete an model"""
        existing = await model.query().filter(lambda x: x.id == model_id).first()
        if not existing:
            raise HTTPException(status_code=404, detail="Artifact not found")
        
        try:
            await existing.delete()
            return {"message": "Artifact deleted successfully"}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    @router.get("/last")
    async def last_model(
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
        ctx: CTX_MODEL = Depends(model_context_parser)
    ):
        """Get the last model with pagination"""
        artifact = await model.query(**ctx).last()
        return artifact
    
    @router.get("/first")
    async def first_model(
        skip: int = Query(default=0, ge=0),
        limit: int = Query(default=10, ge=1, le=100),
        ctx: CTX_MODEL = Depends(model_context_parser)
    ):
        """Get the first model with pagination"""
        artifact = await model.query(**ctx).first()
        return artifact
    
    
    return router
    
    
    
    
 