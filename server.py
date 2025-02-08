from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from promptview.api.message_api import router as message_router
from promptview.api.session_api import router as session_router

# Create FastAPI app
app = FastAPI(
    title="PromptView API",
    description="API for interacting with the PromptView message system",
    version="1.0.0"
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
app.include_router(message_router)
app.include_router(session_router)

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