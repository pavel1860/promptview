import json
from typing import AsyncContextManager, Awaitable, Callable, Set, Type, List, Optional, TypeVar
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from promptview.api.model_router import create_model_router
from promptview.auth.dependencies import get_auth_user
from promptview.auth.user_manager import AuthModel
from promptview.context.model_context import CtxRequest, ModelCtx
from promptview.model3.context import Context
from promptview.model3.query_url_params import parse_query_params, QueryListType
from promptview.model3 import Model, TurnStatus
from promptview.api.utils import build_model_context_parser, get_head, query_filters, unpack_int_env_header, Head
from promptview.model3.block_models.block_log import get_blocks
from promptview.model3.versioning.models import Turn, ExecutionSpan, SpanEvent, Log
from promptview.model3.versioning.models import Branch
from promptview.api.utils import ListParams, get_list_params







def create_turn_router(context_cls: Type[Context] | None = None):
    context_cls = context_cls or Context
    
    async def get_model_ctx(request: Request):
        return await context_cls.from_request(request)
    
    turn_router = create_model_router(Turn, get_model_ctx, exclude_routes={"update"})


    @turn_router.get("/spans")   
    async def get_turn_blocks(
        list_params: ListParams = Depends(get_list_params),
        filters: QueryListType | None = Depends(query_filters),
        ctx = Depends(get_model_ctx)
    ):
        async with ctx:
            turns = await Turn.query().include(
                        ExecutionSpan.query(alias="es").select("*").include(
                            SpanEvent
                        )
                ) \
                .agg("forked_branches", Branch.query(["id"]), on=("id", "forked_from_turn_id")) \
                .where(status = TurnStatus.COMMITTED) \
                .limit(10) \
                .offset(0) \
                .order_by("-created_at") \
                .json()
                
        

            block_ids = []
            log_ids = []
            spans_lookup = {}
            for turn in turns:
                for span in turn['spans']:
                    if span['parent_span_id'] is None:
                        root_span = span
                    spans_lookup[str(span['id'])] = span
                    for event in span['events']:
                        if event['event_type'] == 'block':
                            block_ids.append(event['event_id'])
                        elif event['event_type'] == 'log':
                            log_ids.append(int(event['event_id']))
                



            blocks_lookup = {}
            if block_ids:        
                blocks_lookup = await get_blocks(block_ids)
                
                
            log_lookup = {}
            if log_ids:
                logs = await Log.query().where(lambda l: l.id.isin(log_ids)).json()
                log_lookup = {l['id']: l for l in logs}



            for turn in turns:
                root_span = None
                for span in turn['spans']:
                    if span['parent_span_id'] is None:
                        root_span = span
                    for event in span['events']:
                        if event['event_type'] == 'block':
                            event['data'] = blocks_lookup[event['event_id']]
                        elif event['event_type'] == 'log':
                            event['data'] = log_lookup[int(event['event_id'])]
                        elif event['event_type'] == 'span':
                            event['data'] = spans_lookup[event['event_id']]
                
                if root_span is None and len(turn['spans']) > 0:
                    raise ValueError("No root span found")
                turn['span'] = root_span
                del turn['spans']
                

            return turns    
        
        
        
        
    return turn_router