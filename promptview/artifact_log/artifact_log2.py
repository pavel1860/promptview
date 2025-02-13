"""
A framework for version-controlling Model instances using a git-like architecture.
Models can opt-in to versioning by setting versioned=True in their Config class.

The framework uses the following concepts:
- Head: Points to the current branch and turn
- Branch: A chain of turns, can fork from any turn
- Turn: A commit point containing artifacts
- Artifact: A versioned instance of a Model
"""

import enum
from datetime import datetime
from typing import List, Optional, Type, TypeVar, Generic, Any, Dict, Union, Tuple, Awaitable, cast, Mapping
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Enum,
    create_engine, event, text, select, update, Boolean, Result, Table
)
from sqlalchemy.orm import relationship, declarative_base, Session, Mapped, mapped_column
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.sql.expression import or_, and_
from sqlalchemy_utils import LtreeType
from sqlalchemy_utils.types.ltree import Ltree
from promptview.model.model import Model
from sqlalchemy.ext.asyncio import AsyncSession

Base = declarative_base()
MODEL = TypeVar('MODEL', bound=Model)

class TurnStatus(enum.Enum):
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"

class Head(Base):
    __tablename__ = "heads"
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    turn_id: Mapped[int] = mapped_column(ForeignKey("turns.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    branch: Mapped["Branch"] = relationship("Branch", back_populates="head")
    turn: Mapped["Turn"] = relationship("Turn", back_populates="head")
    branches: Mapped[List["Branch"]] = relationship("Branch", back_populates="head")

class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[Ltree] = mapped_column(LtreeType, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    head: Mapped[Optional["Head"]] = relationship("Head", back_populates="branch", uselist=False)
    turns: Mapped[List["Turn"]] = relationship("Turn", back_populates="branch")

class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    index: Mapped[int] = mapped_column(nullable=False)  # Sequential index within branch
    status: Mapped[TurnStatus] = mapped_column(Enum(TurnStatus), nullable=False, default=TurnStatus.STAGED)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    branch: Mapped["Branch"] = relationship("Branch", back_populates="turns")
    head: Mapped[Optional["Head"]] = relationship("Head", back_populates="turn", uselist=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    artifacts: Mapped[List["BaseArtifact"]] = relationship("BaseArtifact", back_populates="turn")

class BaseArtifact(Base):
    """Base class for all artifact tables."""
    __tablename__ = 'base_artifacts'
    __mapper_args__ = {
        'polymorphic_identity': 'base_artifact',
        'polymorphic_on': 'type'
    }

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    type: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[str] = mapped_column(String(255))
    turn_id: Mapped[int] = mapped_column(Integer, ForeignKey('turns.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    turn = relationship('Turn', back_populates='artifacts')

def create_artifact_table_for_model(model_cls: type) -> type:
    """Create a new artifact table for a model class."""
    table_name = f"{model_cls.__name__.lower()}_artifacts"
    
    # Create the artifact class
    class ModelArtifact(BaseArtifact):
        __tablename__ = table_name
        __mapper_args__ = {
            'polymorphic_identity': table_name,
        }
        
        # Add reference to the model class
        model_class = model_cls
    
    return ModelArtifact

# Register event listener to automatically create artifact tables for versioned models
@event.listens_for(Table, 'after_create')
def create_versioned_artifacts(target, connection, **kw):
    """Create artifact tables for all versioned models after database creation."""
    if hasattr(target, 'model_class'):
        model_cls = target.model_class
        if hasattr(model_cls, 'Config') and hasattr(model_cls.Config, 'versioned') and model_cls.Config.versioned:
            artifact_cls = create_artifact_table_for_model(model_cls)
            if not artifact_cls.__table__.exists(connection):
                artifact_cls.__table__.create(connection)

# Type variable for generic artifact queries
MODEL = TypeVar('MODEL', bound=Model)

def get_artifact_class_for_model(model_cls: Type[MODEL]) -> Type[BaseArtifact]:
    """Get the artifact class for a model."""
    table_name = f"{model_cls.__name__.lower()}_artifacts"
    for cls in BaseArtifact.__subclasses__():
        if cls.__tablename__ == table_name:
            return cls
    raise ValueError(f"No artifact class found for model {model_cls.__name__}")

class ArtifactQuery(Generic[MODEL]):
    """Query builder for artifacts."""
    def __init__(self, session: Session, model_cls: Type[MODEL]):
        self.session = session
        self.model_cls = model_cls
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._turn_filter: Optional[Dict[str, Union[int, str]]] = None
        self._time_filter: Optional[Dict[str, Union[datetime, tuple[datetime, datetime]]]] = None
        self._field_filter: Optional[Dict[str, Any]] = None
        self._include_parent_branches: bool = True

    async def execute(self) -> List[MODEL]:
        """Execute the query and return model instances."""
        # Get the artifact class for this model
        artifact_cls = get_artifact_class_for_model(self.model_cls)
        
        # Build the base query
        query = select(self.model_cls).join(
            artifact_cls,
            artifact_cls.model_id == self.model_cls.id
        ).join(
            Turn,
            artifact_cls.turn_id == Turn.id
        ).join(
            Branch,
            Turn.branch_id == Branch.id
        )
        
        # Apply turn filters
        if self._turn_filter:
            if 'at' in self._turn_filter:
                turn_id = int(self._turn_filter['at'])
                query = query.where(Turn.id == turn_id)
            elif 'up_to' in self._turn_filter:
                turn_id = int(self._turn_filter['up_to'])
                query = query.where(Turn.id <= turn_id)
        
        # Apply time filters
        if self._time_filter:
            if 'at' in self._time_filter:
                timestamp = cast(datetime, self._time_filter['at'])
                query = query.where(Turn.created_at <= timestamp)
            elif 'between' in self._time_filter:
                time_range = cast(tuple[datetime, datetime], self._time_filter['between'])
                query = query.where(Turn.created_at.between(*time_range))
        
        # Apply field filters
        if self._field_filter:
            for field, value in self._field_filter.items():
                query = query.where(getattr(self.model_cls, field) == value)
        
        # Apply limit and offset
        if self._limit is not None:
            query = query.limit(self._limit)
        if self._offset is not None:
            query = query.offset(self._offset)
        
        # Execute query
        if isinstance(self.session, AsyncSession):
            result = await self.session.execute(query)
        else:
            result = await self.session.run_sync(lambda session: session.execute(query))
        return list(result.scalars().all())

    def limit(self, limit: int) -> 'ArtifactQuery[MODEL]':
        """Set the limit for the query."""
        if limit <= 0:
            raise ValueError("Limit must be positive")
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'ArtifactQuery[MODEL]':
        """Set the offset for the query."""
        if offset < 0:
            raise ValueError("Offset must be non-negative")
        self._offset = offset
        return self

    def at_turn(self, turn_id: int) -> "ArtifactQuery[MODEL]":
        """Get artifacts at a specific turn."""
        self._turn_filter = {"type": "at", "turn_id": turn_id}
        return self
    
    def up_to_turn(self, turn_id: int) -> "ArtifactQuery[MODEL]":
        """Get artifacts up to and including a specific turn."""
        self._turn_filter = {"type": "up_to", "turn_id": turn_id}
        return self
    
    def at_time(self, timestamp: datetime) -> "ArtifactQuery[MODEL]":
        """Get artifacts at a specific timestamp."""
        self._time_filter = {"type": "at", "timestamp": timestamp}
        return self
    
    def between(self, start_time: datetime, end_time: datetime) -> "ArtifactQuery[MODEL]":
        """Get artifacts between timestamps."""
        self._time_filter = {"type": "between", "start": start_time, "end": end_time}
        return self
    
    def latest_turn(self) -> "ArtifactQuery[MODEL]":
        """Get artifacts from the latest turn only."""
        self._turn_filter = {"type": "latest"}
        return self
    
    def exclude_parent_branches(self) -> "ArtifactQuery[MODEL]":
        """Only get artifacts from the current branch."""
        self._include_parent_branches = False
        return self
    
    def filter(self, predicate) -> "ArtifactQuery[MODEL]":
        """Filter artifacts by model fields."""
        self._field_filter = predicate
        return self
    
    def first(self) -> Optional[MODEL]:
        """Get the first result."""
        return self.limit(1).execute()[0] if self.execute() else None
    
    def last(self, n: int = None) -> List[MODEL]:
        """Get the last n results."""
        if n is not None:
            self._limit = n
        # TODO: Implement actual query
        return []

class ArtifactLog:
    """
    Main class for managing versioned models and their artifacts.
    """
    def __init__(self, session):
        self.session = session
        self._artifact_tables = {}
    
    def register_model(self, model_cls):
        """
        Register a versioned model and create its artifact table.
        """
        if model_cls.__tablename__ in self._artifact_tables:
            return self._artifact_tables[model_cls.__tablename__]
        
        artifact_cls = create_artifact_table_for_model(model_cls)
        self._artifact_tables[model_cls.__tablename__] = artifact_cls
        return artifact_cls
    
    async def init_head(self, id: int = None) -> Head:
        """
        Initialize a new head with a main branch and initial turn.
        """
        # Create main branch
        branch = Branch(
            name="main",
            path=Ltree("1")  # Root path
        )
        self.session.add(branch)
        await self.session.flush()
        
        # Create initial turn
        turn = Turn(
            branch=branch,
            index=1,
            status=TurnStatus.STAGED
        )
        self.session.add(turn)
        
        # Create head
        head = Head(
            id=id,
            branch=branch,
            turn=turn
        )
        self.session.add(head)
        await self.session.flush()
        
        # Update branch with head reference
        branch.head = head
        await self.session.flush()
        
        return head
    
    async def stage_artifact(self, model) -> BaseArtifact:
        """
        Stage a model instance as an artifact in the current turn.
        """
        if not hasattr(model.__class__.Config, 'versioned') or not model.__class__.Config.versioned:
            raise ValueError(f"Model {model.__class__.__name__} is not versioned")
        
        # Get or create artifact table for this model
        artifact_cls = self.register_model(model.__class__)
        
        # Create artifact
        artifact = artifact_cls(
            turn=self.head.turn,
            record=model
        )
        self.session.add(artifact)
        await self.session.flush()
        
        return artifact
    
    async def commit_turn(self, message: str = None) -> Turn:
        """
        Commit the current turn and create a new one.
        """
        # End current turn
        current_turn = self.head.turn
        current_turn.status = TurnStatus.COMMITTED
        current_turn.ended_at = datetime.utcnow()
        current_turn.message = message
        
        # Create new turn
        new_turn = Turn(
            branch=self.head.branch,
            index=current_turn.index + 1,
            status=TurnStatus.STAGED
        )
        self.session.add(new_turn)
        
        # Update head
        self.head.turn = new_turn
        await self.session.flush()
        
        return new_turn
    
    async def branch_from(self, turn_id: int, name: str = None, check_out: bool = False) -> Branch:
        """
        Create a new branch from a turn.
        """
        # Get source turn
        source_turn = await self.session.get(Turn, turn_id)
        if not source_turn:
            raise ValueError(f"Turn {turn_id} not found")
        
        # Create new branch
        new_branch = Branch(
            name=name,
            parent=source_turn.branch,
            head=self.head,
            path=Ltree(f"{source_turn.branch.path}.{source_turn.id}")
        )
        self.session.add(new_branch)
        await self.session.flush()
        
        # Create initial turn for new branch
        new_turn = Turn(
            branch=new_branch,
            index=1,
            status=TurnStatus.STAGED
        )
        self.session.add(new_turn)
        
        if check_out:
            # Update head to point to new branch
            self.head.branch = new_branch
            self.head.turn = new_turn
        
        await self.session.flush()
        return new_branch
    
    async def checkout_branch(self, branch_id: int) -> None:
        """
        Switch HEAD to a different branch.
        """
        branch = await self.session.get(Branch, branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")
        
        # Get or create staged turn
        turn = await self.session.execute(
            select(Turn)
            .filter(Turn.branch_id == branch_id, Turn.status == TurnStatus.STAGED)
            .order_by(Turn.index.desc())
        ).scalar_one_or_none()
        
        if not turn:
            # Create new turn if none is staged
            turn = Turn(
                branch=branch,
                index=1,
                status=TurnStatus.STAGED
            )
            self.session.add(turn)
        
        # Update head
        self.head.branch = branch
        self.head.turn = turn
        await self.session.flush()
    
    async def revert_turn(self) -> Turn:
        """
        Revert the current turn and create a new one.
        """
        current_turn = self.head.turn
        current_turn.status = TurnStatus.REVERTED
        current_turn.ended_at = datetime.utcnow()
        
        # Create new turn
        new_turn = Turn(
            branch=self.head.branch,
            index=current_turn.index + 1,
            status=TurnStatus.STAGED
        )
        self.session.add(new_turn)
        
        # Update head
        self.head.turn = new_turn
        await self.session.flush()
        
        return new_turn
    
    async def revert_to_turn(self, turn_id: int) -> Turn:
        """
        Revert to a specific turn, marking all later turns as reverted.
        """
        target_turn = await self.session.get(Turn, turn_id)
        if not target_turn:
            raise ValueError(f"Turn {turn_id} not found")
        
        # Mark all later turns as reverted
        await self.session.execute(
            update(Turn)
            .where(
                Turn.branch_id == target_turn.branch_id,
                Turn.index > target_turn.index,
                Turn.status != TurnStatus.REVERTED
            )
            .values(
                status=TurnStatus.REVERTED,
                ended_at=datetime.utcnow()
            )
        )
        
        # Create new turn
        new_turn = Turn(
            branch=target_turn.branch,
            index=target_turn.index + 1,
            status=TurnStatus.STAGED
        )
        self.session.add(new_turn)
        
        # Update head
        self.head.branch = target_turn.branch
        self.head.turn = new_turn
        await self.session.flush()
        
        return new_turn
    
    def get_artifact(self, model_type) -> ArtifactQuery:
        """
        Get a query builder for artifacts.
        """
        if not hasattr(model_type.Config, 'versioned') or not model_type.Config.versioned:
            raise ValueError(f"Model {model_type.__name__} is not versioned")
        
        return ArtifactQuery(self.session, model_type)
    
    async def get_turn(self, turn_id: int) -> Turn:
        """Get a specific turn."""
        turn = await self.session.get(Turn, turn_id)
        if not turn:
            raise ValueError(f"Turn {turn_id} not found")
        return turn
    
    async def get_branch(self, branch_id: int) -> Branch:
        """Get a specific branch."""
        branch = await self.session.get(Branch, branch_id)
        if not branch:
            raise ValueError(f"Branch {branch_id} not found")
        return branch
    
    @property
    def head(self) -> Head:
        """Get the current head."""
        return self.session.query(Head).first()