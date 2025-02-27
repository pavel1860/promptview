import enum
from typing import List
from promptview.model.head_model import HeadModel
from promptview.model.model import Model, Relation, ModelRelation
from promptview.model.fields import ModelField
from pydantic import BaseModel, PrivateAttr




class Result(BaseModel):
    reasoning: str = ModelField(default="")
    score: float = ModelField(default=-1)
    


class TurnResult(BaseModel):
    output: str = ModelField(default="")
    evaluations: list[Result] = ModelField(default=[])
    score: int = ModelField(default=-1)


class TestRunStatus(enum.Enum):
    STARTED = "started"
    SUCCESS = "success"
    FAILURE = "failure"



class TestRun(Model, HeadModel):
    message: str = ModelField(default="")
    results: list[TurnResult] = ModelField(default=[])
    final_score: float = ModelField(default=-1)
    status: TestRunStatus = ModelField(default=TestRunStatus.STARTED)
    test_case_id: int = ModelField(default=None)
        
    class Config:
        database_type="postgres"
        is_detached_head=True


class EvaluatorRelation(BaseModel):
    id: int = ModelField(default=None)



class TestTurn(BaseModel):
    input: str = ModelField(default="")
    output: str = ModelField(default="")
    evaluators: list[EvaluatorRelation] = ModelField(default=[])


class TestInputs(BaseModel):
    turns: List[TestTurn] = ModelField(default=[])


class TestCase(Model, HeadModel):
    title: str = ModelField(default="")
    description: str = ModelField(default="")
    input_turns: List[TestTurn] = ModelField(default=[])
        
    test_runs: TestRun = ModelRelation(key="test_case_id")
    
    class Config:
        database_type="postgres"
        is_detached_head=True
