import asyncio
import json
from typing import Annotated
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from promptview.api.model_router import create_crud_router
from promptview.api.artifact_log_api import router as artifact_log_router
from promptview.artifact_log.artifact_log3 import ArtifactLog
from promptview.model.fields import ModelField
from promptview.model.model import Model
import datetime as dt


# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # This code runs before the server starts serving
#     await instantiate_all_models()
    
#     # Yield to hand control back to FastAPI (start serving)
#     yield


class Message(Model):
    content: str = ModelField(default="")
    role: str = ModelField(default="user")
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    
    class Config: # do not fix this!
        database_type="postgres"
        versioned=True





# Create FastAPI app
app = FastAPI(
    title="PromptView API",
    description="API for interacting with the PromptView message system",
    version="1.0.0",
    # lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(create_crud_router(Message), prefix="/api/model")
app.include_router(artifact_log_router, prefix="/api")




def unpack_int_env_header(request: Request, field: str):    
    value = request.headers.get(field)
    if value is None or value == "null":
        return None
    return int(value)


async def env_ctx(request: Request):
    head_id = unpack_int_env_header(request, "head_id")
    branch_id = unpack_int_env_header(request, "branch_id")
    # with connection_manager.set_env(env or "default"):
        # yield env
    if head_id is None:
        raise HTTPException(status_code=400, detail="head_id is not supported")
    async with ArtifactLog(head_id=head_id, branch_id=branch_id) as art_log:
        yield art_log


# @app.post("/api/chat")
# async def chat(
#     # message: Message,
#     # env: str = Depends(env_ctx)
#     request: Request
#     ):
#     form_data = await request.form()
#     message = json.loads(form_data.get("message"))
#     print(message)
#     return [message, {"message": "Welcome to PromptView API", "role": "assistant"}]

@app.post("/api/chat")
async def chat(
    message_json:  Annotated[str, Form(...)],
    artifact_log: ArtifactLog = Depends(env_ctx)
    ):
    message = Message.model_validate_json(message_json)
    input_time = message.created_at
    await message.save()
    await asyncio.sleep(3)
    response = Message(content="Welcome to PromptView API:" + message.content, role="assistant")
    await response.save()
    output_time = response.created_at
    print(f"input_time: {input_time}, output_time: {output_time}")
    return [response, message]




# Root endpoint
@app.get("/")
async def root():
    return {"message": "Welcome to PromptView API"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True  # Enable auto-reload during development
    ) 