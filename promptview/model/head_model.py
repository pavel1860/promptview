from datetime import datetime
from typing import List
from promptview.artifact_log.artifact_log3 import Branch, Turn
from promptview.artifact_log.artifact_log3 import ArtifactLog
from pydantic import BaseModel


class Head(BaseModel):
    id: int
    main_branch_id: int
    branch_id: int
    turn_id: int
    created_at: datetime
    updated_at: datetime
    # is_detached: bool
    _artifact_log: ArtifactLog
    
    
    @classmethod
    async def from_head_id(cls, head_id: int):
        artifact_log = ArtifactLog()
        _head = await artifact_log.init_head(head_id)         
        head = cls(
            id=_head["id"],
            main_branch_id=_head["main_branch_id"],
            branch_id=_head["branch_id"],
            turn_id=_head["turn_id"],
            created_at=_head["created_at"],
            updated_at=_head["updated_at"],
            # is_detached=_head["is_detached"],
            _artifact_log=artifact_log
        )
        return head

    
    async def checkout(
            self, 
            branch: Branch | None = None, 
            turn: Turn | None = None, 
            head: "Head | None" = None
        ):
        if branch is not None:
            await self._artifact_log.checkout_branch(
                branch_id=branch.id, 
                turn_id=turn.id if turn is not None else None
            )
        if turn is not None:
            raise ValueError("You need to specify a branch")
        if head is not None:
            await self._artifact_log.checkout_head(head_id=head.id)
        return self
    
    
    async def branch_from(self, turn: Turn):
        branch = await self._artifact_log.create_branch(turn_id=turn.id)
        await self.checkout(branch=branch)
        return branch


class HeadModel:
    _head_id: int
    _head: Head | None = None
    
    # def __init__(self, head: Head):
    #     self._head = head

    @property
    def head(self):
        if self._head is None:
            raise ValueError("Head is not initialized")
        return self._head
    
    def checkout(self, turn: int):
        pass
    
    async def after_save(self, **kwargs):
        if "head_id" not in kwargs:
            raise ValueError("Head id is not provided")
        head_id = kwargs.get("head_id")
        self._head = await Head.from_head_id(head_id=head_id)
        return self
    
    async def after_load(self, **kwargs):
        if "head_id" not in kwargs:
            raise ValueError("Head id is not provided")
        head_id = kwargs.get("head_id")
        self._head = await Head.from_head_id(head_id=head_id)
        return self
