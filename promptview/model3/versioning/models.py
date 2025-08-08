import enum
import uuid
import datetime as dt
import contextvars
from typing import List, Type, TypeVar, Self, Any

from promptview.model3.model3 import Model
from promptview.model3.fields import KeyField, ModelField, RelationField  # your new ORM imports

# ContextVars for current branch/turn
_curr_branch = contextvars.ContextVar("curr_branch", default=None)
_curr_turn = contextvars.ContextVar("curr_turn", default=None)


class TurnStatus(enum.StrEnum):
    """Status of a turn in the version history."""
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"
    BRANCH_CREATED = "branch_created"


class Branch(Model):
    _namespace_name = "branches"
    id: int = KeyField(primary_key=True)
    name: str | None = ModelField(default=None)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    forked_from_index: int | None = ModelField(default=None)
    forked_from_turn_id: int | None = ModelField(default=None, foreign_key=True)
    forked_from_branch_id: int | None = ModelField(default=None, foreign_key=True)
    current_index: int = ModelField(default=0)

    turns: List["Turn"] = RelationField("Turn", foreign_key="branch_id")
    children: List["Branch"] = RelationField("Branch", foreign_key="forked_from_branch_id")

    @classmethod
    def current(cls) -> "Branch | None":
        return _curr_branch.get()

    @classmethod
    def set_current(cls, branch: "Branch"):
        _curr_branch.set(branch)


class Turn(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    ended_at: dt.datetime | None = ModelField(default=None)
    index: int = ModelField()
    status: TurnStatus = ModelField(default=TurnStatus.STAGED)
    message: str | None = ModelField(default=None)
    branch_id: int = ModelField(foreign_key=True)
    trace_id: str | None = ModelField(default=None)
    metadata: dict | None = ModelField(default=None)

    forked_branches: List["Branch"] = RelationField("Branch", foreign_key="forked_from_turn_id")

    @classmethod
    def current(cls) -> "Turn | None":
        return _curr_turn.get()

    @classmethod
    def set_current(cls, turn: "Turn"):
        _curr_turn.set(turn)
        
        
    async def commit(self):
        """Mark this turn as committed."""
        self.status = TurnStatus.COMMITTED
        self.ended_at = dt.datetime.now()
        return await self.save()

    async def revert(self, reason: str | None = None):
        """Mark this turn as reverted with an optional reason."""
        self.status = TurnStatus.REVERTED
        self.ended_at = dt.datetime.now()
        if reason:
            self.message = reason
        return await self.save()


class VersionedModel(Model):
    """Mixin for models tied to a specific branch & turn."""
    _is_base = True
    branch_id: int = ModelField(foreign_key=True, foreign_cls=Branch)
    turn_id: int = ModelField(foreign_key=True, foreign_cls=Turn)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    updated_at: dt.datetime | None = ModelField(default=None)
    deleted_at: dt.datetime | None = ModelField(default=None)

    async def save(self, *, branch: Branch | int | None = None, turn: Turn | int | None = None):
        self.branch_id = self._resolve_branch_id(branch)
        self.turn_id = self._resolve_turn_id(turn)
        return await super().save()

    def _resolve_branch_id(self, branch):
        if branch is None:
            branch = Branch.current()
        return branch.id if isinstance(branch, Branch) else branch

    def _resolve_turn_id(self, turn):
        if turn is None:
            turn = Turn.current()
        return turn.id if isinstance(turn, Turn) else turn


class ArtifactModel(VersionedModel):
    """VersionedModel with artifact tracking."""
    _is_base = True
    artifact_id: uuid.UUID = KeyField(default_factory=uuid.uuid4, type="uuid")
    version: int = ModelField(default=1)

    @classmethod
    async def latest(cls, artifact_id: uuid.UUID) -> Self | None:
        """Backend-specific: get latest version per artifact."""
        # Placeholder — will be overridden in backend manager
        return await cls.query().filter(artifact_id=artifact_id).order_by("-version").first()
