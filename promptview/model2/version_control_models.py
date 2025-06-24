from asyncio import Future
from contextlib import asynccontextmanager
import enum
import contextvars
from functools import wraps
from typing import TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable, Generic, List, ParamSpec, Self, Type, TypeVar, overload
import uuid

from pydantic import BaseModel

from promptview.model2.model import Model
from promptview.model2.fields import KeyField, ModelField, RelationField
import datetime as dt

from promptview.model2.postgres.query_set3 import SelectQuerySet
from promptview.model2.postgres.sql.expressions import OrderBy, RawSQL, RawValue, Value
from promptview.model2.postgres.sql.queries import Column, SelectQuery, Subquery
from promptview.model2.relation import Relation
from promptview.utils.function_utils import contextcallable

CURR_TURN = contextvars.ContextVar("curr_turn")
CURR_BRANCH = contextvars.ContextVar("curr_branch")

class TurnStatus(enum.StrEnum):
    """Status of a turn"""
    STAGED = "staged"
    COMMITTED = "committed"
    REVERTED = "reverted"

MODEL = TypeVar("MODEL", bound="Model")
TURN_MODEL = TypeVar("TURN_MODEL", bound="TurnModel")

class VersioningError(Exception):
    pass


class TurnContext(BaseModel):
    branch: "Branch"
    init_params: dict | None = None
    turn: "Turn | None" = None
    
    # def __init__(self, branch: "Branch", init_params: dict | None = None):
    #     self.branch = branch
    #     init_params = init_params or {}
    #     if "message" in init_params:
    #         raise VersioningError("message is reserved for internal use")
    #     if "status" in init_params:
    #         raise VersioningError("status is reserved for internal use")
    #     self.init_params = init_params or {}
    #     self.turn = None
        
    async def __aenter__(self) -> "Turn":
        self.turn = await self.branch.add_turn(**self.init_params)
        self.turn.__enter__()
        return self.turn
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        if self.turn is None:
            raise VersioningError("Turn is not set")
        if exc_type is not None:
            await self.turn.revert()
        else:
            await self.turn.commit()
        self.turn.__exit__(exc_type, exc_value, traceback)



# CTX_RET = TypeVar("CTX_RET")


class Turn(Model):
    id: int = KeyField(primary_key=True)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now, is_default_temporal=True)
    ended_at: dt.datetime | None = ModelField(default=None)
    index: int = ModelField()
    status: TurnStatus = ModelField(default=TurnStatus.STAGED)
    message: str | None = ModelField(default=None)
    branch_id: int = ModelField(foreign_key=True)
    trace_id: str | None = ModelField(default=None)
    forked_branches: Relation["Branch"] = RelationField(foreign_key="forked_from_turn_id")
    _auto_commit: bool = True
    
    # def model_post_init(self, __context): 
        
    
    # @classmethod
    # async def start(cls, branch: "Branch | int | None" = None) -> "Turn":
    #     branch_id = 1
    #     if branch is None:
    #         branch = Branch.current(throw_error=False)
    #         if branch is not None:
    #             branch_id = branch.id
    #     elif isinstance(branch, int):
    #         branch_id = branch
    #     elif isinstance(branch, Branch):
    #         branch_id = branch.id
    #     else:
    #         raise VersioningError("Invalid branch")
    #     turn = await cls(branch_id=branch_id).save()        
    #     return turn
    
    # def __enter__(self):
    #     raise NotImplementedError("Turns should be used with async context manager")
    
    # def __exit__(self, exc_type, exc_value, traceback):
    #     raise NotImplementedError("Turns should be used with async context manager")
    
    
    # async def __aenter__(self):
    #     # self._ctx_token = CURR_TURN.set(self)
    #     self.get_namespace().set_ctx(self)
    #     return self
    
    # async def __aexit__(self, exc_type, exc_value, traceback):
    #     if self._ctx_token is not None:
    #         CURR_TURN.reset(self._ctx_token)
    #     if exc_type is not None:
    #         await self.revert()
    #     elif self._auto_commit:
    #         await self.commit()
    
    # @classmethod
    # def current(cls, throw_error: bool = True):
    #     try:
    #         turn = CURR_TURN.get()
    #     except LookupError:
    #         if throw_error:
    #             raise
    #         else:
    #             return None
    #     return turn
    
    @classmethod
    def list_cte(cls, branch_id: int | None = None, status: TurnStatus | None = None):
        branch_cte = Branch.recursive_cte(branch_id)
        committed_cte = (
            Turn.query()
                .select("id")
                # .where(lambda t: (t.status == status) & (t.index <= RawValue("bh.start_turn_index")))
                .with_cte("branch_hierarchy", branch_cte, recursive=True)
                .order_by("-index")
                # .limit(turns)
        )
        if status is not None:
            committed_cte = committed_cte.where(lambda t: (t.status == status) & (t.index <= RawValue("bh.start_turn_index")))
        else:
            committed_cte = committed_cte.where(lambda t: (t.status != TurnStatus.REVERTED) & (t.index <= RawValue("bh.start_turn_index")))      
        committed_cte.join_cte("branch_hierarchy", "branch_id", "id", "bh")
        return committed_cte
    
    
    async def commit(self):
        self.ended_at = dt.datetime.now()   
        self.status = TurnStatus.COMMITTED
        await self.save()
    
    
    async def revert(self):
        self.ended_at = dt.datetime.now()   
        self.status = TurnStatus.REVERTED
        await self.save()
        
    async def __aenter__(self):
        ns = self.get_namespace()
        self._ctx_token = ns.set_ctx(self)
        return self
        
    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type is not None:
            await self.revert()
        else:
            await self.commit()
        
    # instantiation methods
    # @classmethod
    # def start(cls, branch: "Branch | int | None" = None, **kwargs) -> TurnContext:
    #     branch = Branch.current()
    #     if branch is None:
    #         raise VersioningError("Branch is required")
    #     ns = cls.get_namespace()
    #     fields = ns.iter_fields(keys=False, is_optional=False, exclude={"created_at", "index", "status", "branch_id"})
    #     for field in fields:
    #         if field.is_foreign_key:
    #             value = ns.get_foreign_key_ctx_value(field)
    #             if not field.validate_value(value):
    #                 raise VersioningError(f"Foreign key field {field.name} is required")
    #             kwargs[field.name] = value
    #         else:
    #             raise VersioningError(f"missing required field {field.name} for turn")
            
    #     return TurnContext(branch=branch, init_params=kwargs)
    
    @classmethod
    @contextcallable
    async def start(cls, branch: "Branch | int | None" = None, **kwargs) -> "Turn":
        branch = Branch.current()
        if branch is None:
            raise VersioningError("Branch is required")        
        ns = cls.get_namespace()
        fields = ns.iter_fields(keys=False, is_optional=False, exclude={"created_at", "index", "status", "branch_id"})
        for field in fields:
            if field.is_foreign_key:
                value = ns.get_foreign_key_ctx_value(field)
                if not field.validate_value(value):
                    raise VersioningError(f"Foreign key field {field.name} is required")
                kwargs[field.name] = value
            else:
                raise VersioningError(f"missing required field {field.name} for turn")
        turn = await branch.add_turn(**kwargs)
        return turn
    
    @classmethod
    async def create(cls, branch: "Branch | int | None" = None, **kwargs):
        branch_id = get_branch_id(branch, use_default=False)
        turn = await cls(branch_id=branch_id, **kwargs).save()
        return turn
        
        
        
    # @overload  
    # async def add(self, obj: TURN_MODEL, **kwargs) -> TURN_MODEL:
    #     ...
    
    # @overload
    # async def add(self, obj: "Model", **kwargs) -> "Model":
    #     ...
        
    # async def add(self, obj: "Model", **kwargs) -> "Model":
    #     from promptview.prompt import Block
    #     from promptview.model2.block_model import BlockModel
    #     if not isinstance(obj, TurnModel):
    #         raise VersioningError("Can only add ArtifactModel instances")
    #     if isinstance(obj, Block):
    #         obj = BlockModel.from_block(obj)
    #     obj.turn_id = self.id
    #     obj.branch_id = self.branch_id
    #     return await obj.save()

 


class Branch(Model):
    _namespace_name = "branches"
    id: int = KeyField(primary_key=True)
    name: str | None = ModelField(default=None)
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now, is_default_temporal=True)
    updated_at: dt.datetime = ModelField(default_factory=dt.datetime.now)
    forked_from_index: int | None = ModelField(default=None)
    forked_from_turn_id: int | None = ModelField(default=None, foreign_key=True)
    forked_from_branch_id: int | None = ModelField(default=None, foreign_key=True)
    current_index: int = ModelField(default=0)
    turns: Relation[Turn] = RelationField(foreign_key="branch_id")
    children: Relation["Branch"] = RelationField(foreign_key="forked_from_branch_id")
    
    
    @contextcallable
    async def fork(self, turn: Turn, name: str | None = None):
        index = turn.index
                
        branch = await Branch(
            forked_from_index=index,
            forked_from_turn_id=turn.id,
            current_index=index + 1,
            forked_from_branch_id=self.id,
            name=name,
        ).save()
        return branch    
    
    @classmethod    
    def recursive_cte(cls, branch_id: int | None = None):
        if branch_id is None:
            branch_id = cls.current().id
    
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

        cte = RawSQL(sql)
        return cte
    
    
    async def add_turn(self, message: str | None = None, status: TurnStatus = TurnStatus.STAGED, **kwargs) -> Turn:
        query = f"""
        WITH updated_branch AS (
            UPDATE branches
            SET current_index = current_index + 1
            WHERE id = $1
            RETURNING id, current_index
        ),
        new_turn AS (
            INSERT INTO turns (branch_id, index, created_at, status{"".join([", " + k for k in kwargs.keys()])})
            SELECT id, current_index, current_timestamp, $2{"".join([", $" + str(i) for i in range(3, len(kwargs) + 3)])}
            FROM updated_branch
            RETURNING *
        )
        SELECT * FROM new_turn;
        """        
        turn_ns = Turn.get_namespace()
        
        turn_record = await turn_ns.fetch(query, self.id, status.value, *[kwargs[k] for k in kwargs.keys()])
        if not turn_record:
            raise VersioningError("Failed to add turn")
        # return Turn(**turn_record[0])
        turn = turn_ns.instantiate_model(turn_record[0])
        return turn
        

    
    
    
    

def get_branch_id(branch: "int | Branch | None" = None, use_default: bool = True) -> int:
    if branch is None:
        branch_model = Branch.current_or_none()  
        if branch_model:
            return branch_model.id
        if use_default:
            return 1
        raise VersioningError("Branch is required")
    elif isinstance(branch, int):
        return branch
    elif isinstance(branch, Branch):
        return branch.id
    else:
        raise VersioningError("Invalid branch")
    
    
def get_turn_id_or_none(turn: "int | Turn | None" = None) -> int | None:
    if turn is None:
        turn_model = Turn.current_or_none()
        return turn_model.id if turn_model is not None else None
    elif isinstance(turn, int):
        return turn
    elif isinstance(turn, Turn):
        return turn.id
    else:
        raise VersioningError("Invalid turn")
    
def get_turn_id(turn: "int | Turn | None" = None) -> int:
    turn_id = get_turn_id_or_none(turn)
    if turn_id is None:
        raise VersioningError("Turn is required")
    return turn_id





def create_versioned_cte(branch_id: int, status: TurnStatus | None = None, turns: int | None = None):
    
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

    cte = RawSQL(sql)

    committed_cte = (
        Turn.query()
        .select("id")
        # .where(lambda t: (t.status == status) & (t.index <= RawValue("bh.start_turn_index")))
        .with_cte("branch_hierarchy", cte, recursive=True)
        .order_by("-index")
        # .limit(turns)
    )        
    
    if status is not None:
        committed_cte = committed_cte.where(lambda t: (t.status == status) & (t.index <= RawValue("bh.start_turn_index")))
    else:
        committed_cte = committed_cte.where(lambda t: (t.status != TurnStatus.REVERTED) & (t.index <= RawValue("bh.start_turn_index")))
        
    committed_cte.join_cte("branch_hierarchy", "branch_id", "id", "bh")
    if turns is not None:
        committed_cte = committed_cte.limit(turns)
    return committed_cte

    
class TurnModel(Model):
    _is_base: bool = True
    id: int = KeyField(primary_key=True)    
    branch_id: int = ModelField(foreign_key=True)
    turn_id: int = ModelField(foreign_key=True)    
    created_at: dt.datetime = ModelField(default_factory=dt.datetime.now, is_default_temporal=True)
    updated_at: dt.datetime | None = ModelField(default=None)
    deleted_at: dt.datetime | None = ModelField(default=None)
    
    
    
    def get_turn_id(self, turn: "int | Turn | None" = None) -> int:
        turn_id = get_turn_id_or_none(turn)
        if turn_id is None:
            raise VersioningError(f"Turn is required for {self.__class__.__name__} {self.id}")
        return turn_id

    
    
    @overload
    async def save(self) -> Self:
        ...
    
    @overload
    async def save(self, turn: Turn | int | None = None, branch: Branch | int | None = None) -> Self:
        ...
    
    async def save(self, turn: Turn | int | None = None, branch: Branch | int | None = None):        
        self.turn_id = self.get_turn_id(turn)
        self.branch_id = get_branch_id(branch)
        return await super().save()
    
    
    # @overload
    # @classmethod
    # def query(cls, **kwargs) -> "SelectQuerySet[TurnModel]":
    #     ...
    
    @overload
    @classmethod
    def query(cls: "Type[Self]", **kwargs) -> "SelectQuerySet[Self]":
        ...
    
    
    @overload
    @classmethod
    def query(cls: "Type[Self]", branch: "int | Branch | None" = None, **kwargs) -> "SelectQuerySet[Self]":
        ...
        
    
    @classmethod
    def versioned_cte(cls, cte: "SelectQuerySet[Turn]") -> "SelectQuerySet[Turn]":
        return cte
 
    
    @classmethod
    def query(cls: "Type[Self]", branch: "int | Branch | None" = None, status: TurnStatus = TurnStatus.COMMITTED, turns: int | None = None, **kwargs) -> "SelectQuerySet[Self]":
        """
        Create a query for this model
        
        Args:
            branch: Optional branch ID to query from
        """   
        branch_id = get_branch_id(branch)
        ns = cls.get_namespace()
        turn_cls = Turn.get_namespace().model_class
        query = ns.query(**kwargs)
        query = (
            query.with_cte("turn_hierarchy", turn_cls.list_cte(branch_id, status).limit(turns))
            .join_cte("turn_hierarchy", "turn_id", "id", "th", "INNER")
        )
        return query
    
    
    
    
    
    
    
class ArtifactModel(TurnModel):
    _is_base: bool = True
    artifact_id: uuid.UUID = KeyField(default=None, type="uuid")
    version: int = ModelField(default=1)
    
    
    
    @classmethod
    async def get_artifact(cls: Type[Self], artifact_id: uuid.UUID, version: int | None = None) -> Self:
        """
        Get an artifact model instance by artifact ID and version
        """
        ns = cls.get_namespace()
        data = await ns.get_artifact(artifact_id, version)
        if data is None:
            raise ValueError(f"Artifact '{artifact_id}' with version '{version}' not found")
        instance = cls(**data)
        instance._update_relation_instance()
        return instance
    
    
    async def delete(self, turn: int | Turn | None = None, branch: int | Branch | None = None):
        """
        Delete the artifact model instance from the database
        """
        ns = self.get_namespace()
        data = self._payload_dump()
        result = await ns.delete(data=data, id=self.primary_id, artifact_id=self.artifact_id, version=self.version + 1, branch=branch, turn=turn)
        return result

    
    
    
    @classmethod
    def query(cls: "Type[Self]", branch: "int | Branch | None" = None, status: TurnStatus | None = None, turns: int | None = None, **kwargs) -> "SelectQuerySet[Self]":
        branch_id = get_branch_id(branch)
        ns = cls.get_namespace()
        turn_cls = Turn.get_namespace().model_class
        query = ns.query(**kwargs)
        query = (
            query.with_cte("turn_hierarchy", turn_cls.list_cte(branch_id, status).limit(turns))
            .join_cte("turn_hierarchy", "turn_id", "id", "th", "INNER")
            .distinct_on("artifact_id")
            .order_by("-artifact_id", "-version")
        )
        query = SelectQuerySet(cls).from_subquery(query)
        return query
