from contextlib import asynccontextmanager
import enum
import uuid
import datetime as dt
import contextvars
from typing import TYPE_CHECKING, AsyncGenerator, Callable, List, Literal, Type, TypeVar, Self, Any



from promptview.model3.model3 import Model
from promptview.model3.fields import KeyField, ModelField, RelationField
from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
from promptview.model3.postgres2.rowset import RowsetNode
from promptview.model3.sql.queries import CTENode, RawSQL
from promptview.model3.sql.expressions import RawValue
from promptview.utils.db_connections import PGConnectionManager

if TYPE_CHECKING:
    from promptview.block import Block

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
    
    async def fork_branch(self, turn: "Turn", name: str | None = None):
        branch = await Branch(
            forked_from_index=turn.index,
            forked_from_turn_id=turn.id,
            current_index=turn.index + 1,
            forked_from_branch_id=self.id,
            name=name,
        ).save()
        return branch
    
    
    @classmethod
    async def get_main(cls):
        branch = await cls.get_or_none(1)
        if branch is None:
            branch = await cls(name="main").save()
        return branch
    
    
    @asynccontextmanager
    async def fork(self, turn: "Turn", name: str | None = None) -> AsyncGenerator["Branch", None]:
        branch = await self.fork_branch(turn, name)
        try:
            with branch as b:
                yield b
        except Exception as e:
            # await turn.revert()
            raise e
        
        
    
    @asynccontextmanager  
    async def start_turn(
        self, 
        message: str | None = None, 
        status: TurnStatus = TurnStatus.STAGED,
        **kwargs
    ) -> AsyncGenerator["Turn", None]:
        turn = await self.create_turn(message, status, **kwargs)
        try:
            with turn as t:
                yield t
        except Exception as e:
            await turn.revert(str(e))
            raise e
        finally:
            await turn.commit()
    

    async def create_turn(self, message: str | None = None, status: TurnStatus = TurnStatus.STAGED, auto_commit: bool = True, **kwargs):
        query = f"""
            WITH updated_branch AS (
                UPDATE branches
                SET current_index = current_index + 1
                WHERE id = $1
                RETURNING id, current_index
            ),
            new_turn AS (
                INSERT INTO turns (branch_id, index, created_at, status{"".join([", " + k for k in kwargs.keys()])})
                SELECT id, current_index - 1, current_timestamp, $2{"".join([", $" + str(i) for i in range(3, len(kwargs) + 3)])}
                FROM updated_branch
                RETURNING *
            )
            SELECT * FROM new_turn;
        """   

        if not self.id:
            raise ValueError("Branch ID is not set")
        
        turn_ns = Turn.get_namespace()
        row = await PGConnectionManager.fetch(query, self.id, status.value, *[kwargs[k] for k in kwargs.keys()])
        
        
        # row = await PGConnectionManager.fetch_one(sql, self.id, status.value, message, metadata)
        if not row:
            raise ValueError("Failed to create turn")
        if turn_ns._model_cls is None:
            raise ValueError("Turn namespace is not initialized")
        # turn = Turn(**row[0])
        turn = turn_ns._model_cls(**row[0])
        turn.branch_id = self.id
        turn._auto_commit = auto_commit
        return turn

        
        

        # finally:
            # await turn.commit()
        

    
    @classmethod
    def recursive_query(cls, branch_id: int) -> PgSelectQuerySet["Branch"]:
        sql = f"""
            SELECT
                id,
                name,
                forked_from_index,
                forked_from_branch_id,
                current_index AS start_turn_index
            FROM branches
            WHERE id = {branch_id}

            UNION ALL

            SELECT
                b.id,
                b.name,
                b.forked_from_index,
                b.forked_from_branch_id,
                bh.forked_from_index AS start_turn_index
            FROM branches b
            JOIN branch_hierarchy bh ON b.id = bh.forked_from_branch_id
        """
        return PgSelectQuerySet(Branch, alias="branch_hierarchy", recursive=True).raw_sql(sql, [
            "id", 
            "name", 
            "forked_from_index", 
            "forked_from_branch_id", 
            ("current_index", "start_turn_index")
        ])
        # return RowsetNode("branch_hierarchy", RawSQL(sql), model=Branch, key="id", recursive=True)

    



class Turn(Model):
    # _is_base: bool = True
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    ended_at: dt.datetime | None = ModelField(default=None)
    index: int = ModelField(order_by=True)
    status: TurnStatus = ModelField(default=TurnStatus.STAGED)
    message: str | None = ModelField(default=None)
    branch_id: int = ModelField(foreign_key=True)
    trace_id: str | None = ModelField(default=None)
    metadata: dict | None = ModelField(default=None)
    spans: List["ExecutionSpan"] = RelationField(foreign_key="turn_id")
    _auto_commit: bool = True

    # forked_branches: List["Branch"] = RelationField("Branch", foreign_key="forked_from_turn_id")
    @classmethod
    def blocks(cls):
        from promptview.model3.block_models.block_log import parse_block_tree_turn
        return cls.query().include(
            BlockTree.query(alias="bt").select("*").include(
                BlockNode.query(alias="bn").select("*").include(
                    BlockModel.query(alias="bm").select("*")
                )
            )
        ).parse(parse_block_tree_turn)
        
        
    async def add_block(self, block: "Block", index: int, span_id: uuid.UUID | None = None):
        from promptview.model3.block_models.block_log import insert_block
        return await insert_block(block, index, self.branch_id, self.id, span_id)
        
        
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
    
    @classmethod
    def _resolve_branch_id(cls, branch: Branch | None = None) -> int:
        if branch is not None:
            return branch.id
        curr_branch = Branch.current()
        if curr_branch is None:
            raise ValueError("No branch in context for a versioned query and no branch was provided.")
        return curr_branch.id
    
    @classmethod
    def versioned_query(
        cls: Type[Self], 
        fields: list[str] | None = None, 
        branch: Branch | None = None, 
        **kwargs
    ) -> "PgSelectQuerySet[Self]":
        from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
        branch_id = cls._resolve_branch_id(branch)
        branch_cte = Branch.recursive_query(branch_id)
        col = branch_cte.get_field("start_turn_index")
        query = (
            PgSelectQuerySet(cls) \
            .use_cte(branch_cte, name="branch_hierarchy", alias="bh", on=("branch_id", "id"))    
            .where(lambda t: (t.index <= RawValue("bh.start_turn_index")))
            # .where(lambda t: (t.index <= branch_cte.get_field("start_turn_index")))
        )
        return cls.query_extra(query, **kwargs)
    
    @classmethod    
    def query_extra(cls: Type[Self], query: "PgSelectQuerySet[Self]", **kwargs) -> "PgSelectQuerySet[Self]":
        return query
    
        


class VersionedModel(Model):
    """Mixin for models tied to a specific branch & turn."""
    _is_base = True
    branch_id: int = ModelField(foreign_key=True, foreign_cls=Branch)
    turn_id: int = ModelField(foreign_key=True, foreign_cls=Turn)
    turn: "Turn | None" = RelationField("Turn", primary_key="turn_id", foreign_key="id")
    branch: "Branch | None" = RelationField("Branch", foreign_key="id")
    

    async def save(self, *, branch: Branch | int | None = None, turn: Turn | int | None = None):
        if self.branch_id is None:
            self.branch_id = self._resolve_branch_id(branch)
        if self.turn_id is None:
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
    
    @classmethod
    def vquery(cls, fields: list[str] | None = None, alias: str | None = None, **kwargs):
        from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
        return (
            PgSelectQuerySet(cls, alias=alias) \
            .use_cte(
                Turn.versioned_query().select(fields or "*").where(status=TurnStatus.COMMITTED),
                name="committed_turns",
                alias="ct",
            )
        )



class BlockModel(Model):
    _namespace_name: str = "blocks"
    id: str = KeyField(primary_key=True)
    # created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    content: str | None = ModelField(default=None)
    json_content: dict | None = ModelField(default=None)    
    

class BlockNode(Model):
    id: int = KeyField(primary_key=True)
    tree_id: uuid.UUID = ModelField(foreign_key=True)
    path: str = ModelField(db_type="LTREE")
    type: str = ModelField()
    block_id: str = ModelField(foreign_key=True)
    styles: list[str] | None = ModelField(default=None)
    role: str | None = ModelField(default=None)
    tags: list[str] | None = ModelField(default=None)
    attrs: dict | None = ModelField(default=None)
    block: "BlockModel" = RelationField(primary_key="block_id", foreign_key="id")
    tree: "BlockTree" = RelationField(primary_key="tree_id", foreign_key="id")
    
    @classmethod
    async def block_query(cls, cte):
        from promptview.model3.block_models.block_log import pack_block
        from promptview.model3.sql.queries import Column
        records = await cls.query([
            Column("styles", "bn"),
            Column("role", "bn"),
            Column("tags", "bn"),
            Column("path", "bn"),
            Column("attrs", "bn"),
            Column("type", "bn"),
            Column("content", "bsm"),
            Column("json_content", "bsm"),            
        ], alias="bn") \
        .use_cte(cte,"tree_cte", alias="btc") \
        .join(BlockModel.query(["content", "json_content"], alias="bsm"), on=("block_id", "id")) \
        .where(lambda b: (b.tree_id == RawValue("btc.id"))).print().json()
        return pack_block(records)
     
        
class BlockTree(VersionedModel):
    id: uuid.UUID = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    nodes: List[BlockNode] = RelationField(foreign_key="tree_id")
    span_id: uuid.UUID | None = ModelField(foreign_key=True)
    index: int = ModelField()
    


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





span_type_enum = Literal["component", "stream", "llm"]



class Log(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    message: str = ModelField()
    level: Literal["info", "warning", "error"] = ModelField()
    


class SpanEvent(VersionedModel):
    id: int = KeyField(primary_key=True)    
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    event_type: Literal["block", "span", "log", "model"] = ModelField()
    table: str | None = ModelField(default=None)
    index: int = ModelField()
    span_id: uuid.UUID = ModelField(foreign_key=True)
    event_id: str = ModelField()
    
    

class ExecutionSpan(VersionedModel):
    """Represents a single execution unit (component call, stream, etc.)"""
    id: uuid.UUID = KeyField(primary_key=True)
    name: str = ModelField()  # Function/component name
    span_type: span_type_enum = ModelField()
    parent_span_id: uuid.UUID | None = ModelField(foreign_key=True)
    turn_id: int = ModelField(foreign_key=True)
    branch_id: int = ModelField(foreign_key=True)
    start_time: dt.datetime = ModelField(default_factory=dt.datetime.now)
    end_time: dt.datetime | None = ModelField(default=None)
    depth: int = ModelField(default=0)  # Nesting level
    metadata: dict[str, Any] = ModelField(default={})
    status: Literal["running", "completed", "failed"] = ModelField(default="running")
    index: int = ModelField()
    
    # Relations
    events: List["SpanEvent"] = RelationField(foreign_key="span_id")
    # events: List[Event] = RelationField(foreign_key="execution_span_id")
    block_trees: List[BlockTree] = RelationField(foreign_key="span_id")
    
    
    
    async def add_block(self, block: "Block", index: int):
        from promptview.model3.block_models.block_log import insert_block
        tree_id = await insert_block(block, index, self.branch_id, self.turn_id, self.id)
        event = await SpanEvent(
            span_id=self.id,
            event_type="block",
            event_id=tree_id,
            index=index
        ).save()
        return event
    
    
    async def add_span(self, span: "ExecutionSpan", index: int):
        return await SpanEvent(
            span_id=self.id,
            event_type="span",
            event_id=str(span.id),
            index=index
        ).save()
    
    async def add_log(self, log: "Log", index: int):
        return await SpanEvent(
            span_id=self.id,
            event_type="log",
            event_id=str(log.id),
            index=index
        ).save()
        
        
    async def add_model(self, model: "Model", index: int):
        return await SpanEvent(
            span_id=self.id,
            event_type="model",
            event_id=str(model.id),
            table=model._namespace_name,
            index=index
        ).save()
        
        
    
    