


import json
from typing import Any, Literal, TypedDict, Unpack
from pydantic import BaseModel, Field
import uuid
from datetime import datetime



LlmStreamType = Literal["stream_start", "message_delta", "stream_end", "stream_error"]

AgentMessageType = Literal["agent_message"]

EventType = LlmStreamType



class EventParams(TypedDict, total=False):
    timestamp: int | None
    error: str | None




class Event:
    __slots__ = [
        "type",
        "timestamp",
        "payload",
        "error",
    ]
    def __init__(
        self, 
        type: EventType,
        payload: Any,
        **kwargs: Unpack[EventParams]):
        self.type = type
        self.payload = payload
        self.timestamp: int | None = kwargs.get("timestamp")
        self.error: str | None = kwargs.get("error")
        
        
    def payload_to_dict(self):
        if hasattr(self.payload, "model_dump"):
            return self.payload.model_dump()
        elif hasattr(self.payload, "to_dict"):
            return self.payload.to_dict()
        else:
            return self.payload
        
    def to_json(self):
        payload = self.payload_to_dict()
        
        dump = {
            "type": self.type,
            "payload": payload,
        }        
        if self.error:
            dump["error"] = self.error
            
        if self.timestamp:
            dump["timestamp"] = self.timestamp
            
        return json.dumps(dump)
    
    def to_ndjson(self):
        return self.to_json() + "\n"
    
    
    
    
