from dotenv import load_dotenv
load_dotenv()

import json
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, APIRouter, Depends, WebSocket
from pydantic import BaseModel
from typing import Any
from faststream.rabbit.fastapi import RabbitRouter
import os





# Socket Manager for handling WebSocket connections
class SocketManager:
    def __init__(self) -> None:
        self._active_connections = {}    
    
    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._active_connections[user_id] = websocket
        
    async def disconnect(self, user_id: str) -> None:
        socket = self._active_connections.pop(user_id)
        await socket.close()
        
    async def send_message(self, user_id: str, message: dict) -> None:
        socket = self._active_connections.get(user_id)
        if socket:
            await socket.send_text(json.dumps(message))

socket_manager = SocketManager()

# WebSocket Router
router = APIRouter(prefix="/subscribe", tags=["subscribe"])

def get_user_id(websocket: WebSocket) -> str:
    user_id = websocket.query_params.get("user_id")
    if not user_id:
        raise ValueError("User ID not provided")
    return user_id

@router.websocket("/socket")
async def chat_endpoint(websocket: WebSocket, user_id: str = Depends(get_user_id)):
    await socket_manager.connect(user_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Process received data if needed
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        await socket_manager.disconnect(user_id)

# RabbitMQ setup
rabbitmq_url = os.getenv('RABBITMQ_URL', 'amqp://guest:guest@localhost:5672/')
print(f"RabbitMQ URL: {rabbitmq_url}")
rabbit_router = RabbitRouter(rabbitmq_url)

class Message(BaseModel):
    user_id: str    
    content: Any

@rabbit_router.subscriber("message")
async def message_handler(message: Message):
    print(f"Received message for user {message.user_id}")
    await socket_manager.send_message(message.user_id, message.content)

async def connect_with_retry(max_retries=5, retry_delay=5):
    """Attempt to connect to RabbitMQ with retries"""
    for attempt in range(max_retries):
        try:
            await rabbit_router.broker.connect()
            print("Successfully connected to RabbitMQ")
            return
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            print(f"Failed to connect to RabbitMQ (attempt {attempt + 1}/{max_retries}): {str(e)}")
            await asyncio.sleep(retry_delay)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        await connect_with_retry()
        yield
    finally:
        # Shutdown
        await rabbit_router.broker.close()

# Create FastAPI app
app = FastAPI(
    title="Socket Manager",
    description="WebSocket manager with RabbitMQ integration",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(router)
app.include_router(rabbit_router)