from typing import List, Literal
from pydantic import BaseModel
from promptview.model import NamespaceManager
from promptview.model.relation import Relation
# from promptview.testing import TestCase, TestRun, TestTurn, TestInputs
from promptview.model import Branch, Turn as TurnBase

from datetime import datetime
from promptview.model.fields import KeyField, ModelField, RelationField
from promptview.model.version_control_models import Turn, TurnModel


from promptview.model import Model, ModelField



class Evaluation(BaseModel):
    evaluator: str = ModelField(default="", description="the evaluator that was used to evaluate the turn")
    reasoning: str = ModelField(default="", description="step by step reasoning about the response, differences between expected and actual output and is it confirms with the requirements")
    score: float | None = ModelField(default=None, description="the score of the test run")
    run_id: str = ModelField(default="", description="the id of the test run")



class TurnEval(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    turn_id: int = ModelField(default=None, foreign_key=True)
    test_run_id: int = ModelField(default=None, foreign_key=True)
    score: float | None = ModelField(default=None, description="the score of the test run")
    evaluations: List[Evaluation] = ModelField(default=[], description="the evaluator that was used to evaluate the turn")
    trace_id: str = ModelField(default="", description="the id of the test run")


    
    
class TestRun(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    test_case_id: int = ModelField(default=None, foreign_key=True)
    branch_id: int = ModelField(default=1, description="the branch this test run belongs to")
    score: float | None = ModelField(default=None, description="the score of the test run")
    status: Literal["running", "success", "failure"] = ModelField(default="running", description="the status of the test run")
    turn_evals: Relation[TurnEval] = RelationField(foreign_key="test_run_id")
    
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback):        
        if exc_type is not None:
            self.status = "failure"
        else:
            self.status = "success"
        await self.save()

class EvaluatorConfig(BaseModel):
    name: str = ModelField(default="")
    parameters: dict = ModelField(default={})

class InputTurn(BaseModel):
    input: str = ModelField(default="")
    expected: List[str] = ModelField(default=[])
    evaluators: List[EvaluatorConfig] = ModelField(default=[])
    
    
class PromptEval(BaseModel):
    description: str = ModelField(default="")
    



    


class TestCase(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    title: str = ModelField(default="")
    description: str = ModelField(default="")
    evaluators: dict[int, PromptEval] = ModelField(default={})
    branch_id: int = ModelField(default=1, foreign_key=True, description="the branch this test case belongs to")
    # start_turn_id: int = ModelField(foreign_key=True, description="the turn this test case will start from")
    # end_turn_id: int = ModelField(foreign_key=True, description="the turn this test case will end at")
    # limit: int = ModelField(description="the number of turns to test")
    user_id: int = ModelField(description="the user this test case belongs to")
    test_runs: Relation[TestRun] = RelationField(foreign_key="test_case_id")
    turns: Relation[Turn] = RelationField(foreign_key="test_case_id")
