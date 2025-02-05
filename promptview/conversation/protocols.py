from typing import Protocol
import datetime as dt



class BaseProto(Protocol):
    id: int
    created_at: dt.datetime
    
    @staticmethod
    async def get(id: int) -> "BaseProto":
        ...

    async def save(self) -> "BaseProto":
        ...




class BranchProto(BaseProto):
    id: int
    created_at: dt.datetime
    forked_from_message: "MessageProto | None"
    forked_from_message_order: int | None
    



class TurnProto(BaseProto):
    id: int
    created_at: dt.datetime
    branch: BranchProto
    messages: list["MessageProto"]
    local_state: dict
    




class MessageProto(BaseProto):
    id: int
    created_at: dt.datetime
    role: str
    name: str | None
    content: str
    blocks: list[dict] | None
    run_id: str
    platform_id: str | None
    ref_id: str | None
    branch_order: int
    branch: BranchProto
    turn: TurnProto

    
    