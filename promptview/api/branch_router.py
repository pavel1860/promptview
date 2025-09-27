from typing import Type
from promptview.model3 import Branch
from promptview.api.model_router import create_model_router
from promptview.model3.context import Context
from fastapi import Request


def create_branch_router(context_cls: Type[Context] | None = None):
    context_cls = context_cls or Context
    
    def get_model_ctx(request: Request):
        return context_cls.from_request(request)
    
    branch_router = create_model_router(Branch, get_model_ctx, exclude_routes={"update"})

    return branch_router