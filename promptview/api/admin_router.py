from fastapi import APIRouter
from promptview.api.message_api import router as message_router
from promptview.api.session_api import router as session_router

admin_router = APIRouter(prefix="/api")

# Include the Users router
admin_router.include_router(
    message_router,
    tags=["messages"],  # Optional: used for grouping in OpenAPI docs
)

# Include the Items router
admin_router.include_router(
    session_router,
    tags=["sessions"],  # Optional: used for grouping in OpenAPI docs
)
