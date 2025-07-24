


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
    index: int | None




class Event:
    __slots__ = [
        "type",
        "timestamp",
        "payload",
        "error",
        "index",
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
        self.index: int | None = kwargs.get("index")
        
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
            "index": self.index,
        }        
        if self.error:
            dump["error"] = self.error
            
        if self.timestamp:
            dump["timestamp"] = self.timestamp
            
        return json.dumps(dump)
    
    def to_ndjson(self):
        return self.to_json() + "\n"
    
    
    
    

    
from pydantic import BaseModel, Field
from typing import Any, Literal, Protocol, Union, Optional, List, Dict
from datetime import datetime



class Serializeble(Protocol):
    
    def model_dump(self) -> dict:
        ...
    


# -- Base event --
class BaseEvent(BaseModel):
    turn_id: int
    timestamp: Optional[datetime] = None


# -- Event: Stream Start --
class StreamStart(BaseEvent):
    type: Literal["stream_start"] = "stream_start"

class MessageDelta(BaseEvent):
    type: Literal["message_delta"] = "message_delta"
    payload: Any

class StreamEnd(BaseEvent):
    type: Literal["stream_end"] = "stream_end"
    response: Any
    done: Literal[True] = True

# -- Tool Call Info --
class ToolCallObject(BaseModel):
    id: str
    name: str
    args: Dict
    status: Literal["started", "completed", "errored"]
    output: Optional[Dict] = None
    error: Optional[str] = None


# -- Event: Tool Call --
class ToolCallEvent(BaseEvent):
    type: Literal["tool_call"]
    tool_calls: List[ToolCallObject]


# -- Event: State Update --
class StateUpdate(BaseEvent):
    type: Literal["state_update"]
    state: Dict[str, Dict]


# -- Event: Agent Final Output --
class AgentResponse(BaseEvent):
    type: Literal["agent_response"]
    message: Dict


# -- Event: Developer Log Line --
class LogEvent(BaseEvent):
    type: Literal["log"]
    content: str


# -- Event: Trace Info (execution stack, context diffs) --
class TraceEvent(BaseEvent):
    type: Literal["trace"]
    state: Dict


# -- Event: Error Info --
class ErrorEvent(BaseEvent):
    type: Literal["error"]
    content: str


# -- Union: All Stream Events --
StreamEvent = Union[
    StreamStart,
    MessageDelta,
    StreamEnd,
    ToolCallEvent,
    StateUpdate,
    AgentResponse,
    LogEvent,
    TraceEvent,
    ErrorEvent,
]
