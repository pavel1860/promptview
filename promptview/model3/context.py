from typing import TYPE_CHECKING, Iterator, Type
from promptview.model3.model3 import Model
from promptview.model3.postgres2.pg_query_set import PgSelectQuerySet
from promptview.model3.versioning.models import Branch, Turn, TurnStatus, VersionedModel
from dataclasses import dataclass
if TYPE_CHECKING:
    from fastapi import Request



@dataclass
class LoadTurn:
    turn_id: int
    
@dataclass
class LoadBranch:
    branch_id: int
    
    
@dataclass
class ForkTurn:
    turn: Turn | None = None
    turn_id: int | None = None

@dataclass
class ForkBranch:
    branch_id: int
    
    
@dataclass
class StartTurn:
    branch_id: int | None = None
    auto_commit: bool = True
    

class Context:
    
    
    
    def __init__(
        self,
        *models: Model,
        branch: Branch | None = None,
        turn: Turn | None = None,
        branch_id: int | None = None,
        turn_id: int | None = None,
        request: "Request | None" = None,
    ):
        self.ctx_models = {m.__class__.__name__:m for m in models}
        self.tasks = []
        if branch_id is not None:
            self.tasks.append(LoadBranch(branch_id=branch_id))
        if turn_id is not None:
            self.tasks.append(LoadTurn(turn_id=turn_id))
            
        self._branch = branch
        self._turn = turn
        self.request = request
        
    @property
    def request_id(self):
        if self.request is not None:
            return self.request.state.request_id
        return None
        
    @classmethod
    async def from_request(cls, request: "Request"):
        ctx_args = request.state.get("ctx")
        if ctx_args is None:
            raise ValueError("ctx is not set")
        ctx = cls(**ctx_args)    
        return ctx
    
    @classmethod
    async def from_kwargs(cls, **kwargs):
        ctx = cls(**kwargs)    
        return ctx

        
    @property
    def branch(self) -> Branch:
        if self._branch is None:
            raise ValueError("Branch not found")
        return self._branch
    
    @property
    def turn(self) -> Turn:
        if self._turn is None:
            raise ValueError("Turn not found")
        return self._turn
    
    async def get_branch(self) -> Branch:
        return await Branch.get_main()
        
    
    async def _get_branch(self) -> Branch:
        if self._branch is None:
            self._branch = await Branch.get_main()
        return self._branch
    
        # if self._branch is not None:
        #     return self.branch
        # elif self.branch_id is not None:
        #     self._branch = await Branch.get(self.branch_id)
        #     return self.branch
        # else:
        #     self._branch = await self.get_branch()
        #     return self.branch
        
    
    def start_turn(self, auto_commit: bool = True) -> "Context":
        self.tasks.append(StartTurn(auto_commit=auto_commit))
        return self
    
    def fork(self, turn: Turn | None = None, turn_id: int | None = None) -> "Context":
        self.tasks.append(ForkTurn(turn=turn, turn_id=turn_id))
        return self
    
    # def fork(self, branch: Branch | None = None)
    
    async def _handle_tasks(self) -> Branch:
        for task in self.tasks:
            if isinstance(task, LoadBranch):
                self._branch = await Branch.get(task.branch_id)
            elif isinstance(task, LoadTurn):
                self._turn = await Turn.get(task.turn_id)                
            elif isinstance(task, ForkTurn):
                if task.turn is not None:
                    branch = await self._get_branch()
                    self._branch = await branch.fork_branch(task.turn)
                elif task.turn_id is not None:
                    branch = await self._get_branch()
                    turn = await Turn.get(task.turn_id)
                    self._branch = await branch.fork_branch(turn)
                else:
                    branch = await self._get_branch()
                    turn = await Turn.query().where(branch_id=branch.id).last()
                    self._branch = await branch.fork_branch(turn)
            elif isinstance(task, StartTurn):
                branch = await self._get_branch()
                self._turn = await branch.create_turn(auto_commit=task.auto_commit)
            

        if self._branch is None:
            branch = await self._get_branch()
        # if self.turn is None:
            # raise ValueError("Turn not found")
                
        return self.branch
    
    def get_models(self):
        v_models = []
        models = []
        for model in self.ctx_models.values():
            if isinstance(model, VersionedModel):
                v_models.append(model)
            else:
                models.append(model)
        return v_models, models
                
        
    async def __aenter__(self):
        branch = await self._handle_tasks()
        v_models, models = self.get_models()
        for model in models:
            model.__enter__()
        branch.__enter__()
        if self._turn is not None:
            await self._turn.__aenter__()
        for model in v_models:
            model.__enter__()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):
        v_models, models = self.get_models()
        for model in reversed(v_models):
            model.__exit__(exc_type, exc_value, traceback)
        if self._turn is not None:
            await self._turn.__aexit__(exc_type, exc_value, traceback)
        self.branch.__exit__(exc_type, exc_value, traceback)
        for model in reversed(models):
            model.__exit__(exc_type, exc_value, traceback)
              
            
            
    def select(self, target: Type[Model] | PgSelectQuerySet[Model], fields: list[str] | None = None, alias: str | None = None) -> "PgSelectQuerySet[Model]":
        turn_cte = Turn.vquery().select("*").where(status=TurnStatus.COMMITTED)
        # query = model.query().use_cte(turn_cte, "committed_turns", alias="ct")
        if isinstance(target, PgSelectQuerySet):
            query = target 
        else:
            query = target.query().select(*fields if fields else "*")
            # query = PgSelectQuerySet(target, alias=alias) \
            #     .select(*fields if fields else "*")        
        query.use_cte(
            turn_cte,
            name="committed_turns",
            alias="ct",
        )
        return query