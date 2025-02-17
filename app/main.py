from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from promptview.api.model_router import create_crud_router
from promptview.model.fields import ModelField
from promptview.model.model import Model



# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     # This code runs before the server starts serving
#     await instantiate_all_models()
    
#     # Yield to hand control back to FastAPI (start serving)
#     yield


class Message(Model):
    content: str = ModelField(default="")
    role: str = ModelField(default="user")
    
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
app.include_router(create_crud_router(Message))



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