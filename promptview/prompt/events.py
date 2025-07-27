


import json
from typing import Any, Literal, TypedDict, Unpack
from pydantic import BaseModel, Field
import uuid
import datetime as dt



LlmStreamType = Literal["stream_start", "message_delta", "stream_end", "stream_error"]

SpanEventType = Literal["span_start", "span_end"]

MessageType = Literal["user_message", "assistant_message"]

EventType = LlmStreamType | MessageType | SpanEventType



class EventParams(TypedDict, total=False):
    timestamp: int | None
    error: str | None
    index: int | None
    request_id: str | None




class Event:
    __slots__ = [
        "type",
        "span",
        "timestamp",
        "payload",
        "error",
        "index",
        "request_id",
    ]
    def __init__(
        self, 
        type: EventType,
        payload: Any,        
        span: str | None = None,        
        **kwargs: Unpack[EventParams]):
        self.type = type
        self.span = span
        self.payload = payload
        self.timestamp: int | None = kwargs.get("timestamp")
        self.error: str | None = kwargs.get("error")
        self.index: int | None = kwargs.get("index")
        self.request_id: str | None = kwargs.get("request_id")
        
    def payload_to_dict(self):
        if hasattr(self.payload, "model_dump"):
            return self.payload.model_dump()
        elif hasattr(self.payload, "to_dict"):
            return self.payload.to_dict()
        else:
            return self.payload
        
        
    @staticmethod
    def _json_default(obj):
        if isinstance(obj, dt.datetime):
            return obj.isoformat()
        if isinstance(obj, dt.date):
            return obj.isoformat()
        # Add more types if needed
        raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")
        
    def to_json(self):
        payload = self.payload_to_dict()
        
        dump = {
            "type": self.type,
            "span": self.span,
            "payload": payload,
            "index": self.index,
            "request_id": self.request_id,
        }        
        if self.error:
            dump["error"] = self.error
            
        if self.timestamp:
            dump["timestamp"] = self.timestamp
            
        return json.dumps(dump, default=self._json_default)
    
    def to_ndjson(self):
        return self.to_json() + "\n"
    
    def __repr__(self):
        return f"Event(type={self.type}, span={self.span}, payload={self.payload}, index={self.index}, request_id={self.request_id})"
    
    

    
from pydantic import BaseModel, Field
from typing import Any, Literal, Protocol, Union, Optional, List, Dict
import datetime as dt



class Serializeble(Protocol):
    
    def model_dump(self) -> dict:
        ...
    


# -- Base event --
class BaseEvent(BaseModel):
    turn_id: int
    timestamp: Optional[dt.datetime] = None


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
