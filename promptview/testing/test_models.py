from typing import List, Literal
from pydantic import BaseModel
from promptview.model2 import NamespaceManager
from promptview.model2.relation import Relation
# from promptview.testing import TestCase, TestRun, TestTurn, TestInputs
from promptview.model2 import Branch, Turn as TurnBase

from datetime import datetime
from promptview.model2.fields import KeyField, ModelField, RelationField
from promptview.model2.version_control_models import TurnModel


from promptview.model2 import Model, ModelField





class TurnEval(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    turn_id: int = ModelField(default=None, foreign_key=True)
    test_run_id: int = ModelField(default=None, foreign_key=True)
    score: float | None = ModelField(default=None, description="the score of the test run")
    evaluator: str = ModelField(default="", description="the evaluator that was used to evaluate the turn")
    reasoning: str = ModelField(default="", description="step by step reasoning about the response, differences between expected and actual output and is it confirms with the requirements")


    
    
class TestRun(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    test_case_id: int = ModelField(default=None, foreign_key=True)
    branch_id: int = ModelField(default=1, description="the branch this test run belongs to")
    score: float | None = ModelField(default=None, description="the score of the test run")
    status: Literal["running", "success", "failure"] = ModelField(default="running", description="the status of the test run")
    evaluations: Relation[TurnEval] = RelationField(foreign_key="test_run_id")



class InputTurn(BaseModel):
    input: str = ModelField(default="")
    expected: List[str] = ModelField(default=[])
    evaluators: List[str] = ModelField(default=[])
   

class TestCase(Model):
    id: int = KeyField(primary_key=True)
    created_at: datetime = ModelField(default_factory=datetime.now, is_default_temporal=True)
    updated_at: datetime = ModelField(default_factory=datetime.now)
    title: str = ModelField(default="")
    description: str = ModelField(default="")
    input_turns: list[InputTurn] = ModelField(default=[])
    branch_id: int = ModelField(default=1, description="the branch this test case belongs to")
    turn_id: int = ModelField(default=1, description="the turn this test case will start from")
    
    test_runs: Relation[TestRun] = RelationField(foreign_key="test_case_id")
