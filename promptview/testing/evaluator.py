from pydantic import BaseModel, Field
from promptview.prompt.block2 import StrBlock
from promptview.prompt.output_format import OutputModel
from promptview import prompt, Depends, OpenAiLLM
from promptview.model.model import Model, Relation, ModelRelation
from promptview.model.fields import ModelField



class EvalResponse(OutputModel):
    reasoning: str = Field(..., description="step by step reasoning about the evaluation of the response")
    score: int = Field(..., description="the score of the response. should be an integer number between 1 and 10")

    @classmethod
    def render(cls) -> StrBlock | None:
        from promptview import block as b
        with b.title("Rules", bullet="*") as rules:
            b.li += "you have to use the output format and the reasoning to evaluate the response"
            b.li += "you have to give a true score for the response."
            return rules



@prompt()
async def evaluate_prompt(task: str, response: str, llm: OpenAiLLM = Depends(OpenAiLLM)):
    from promptview import block as b
    with b("""
        you are a helpful assistant that evaluates the response.
        You need to evaluate the response based on the given task and rules.
    """, role="system") as sm:
        with b.title("Task"):
            b += task
        EvalResponse.to_block()
    
    with b.title("Response to evaluate", role="user") as target:
        b += response
    
    res = await llm([sm, target]).output_format(EvalResponse)
    return res




class Evaluator(Model):
    name: str = ModelField()    
    task: str = ModelField()
    rules: list[str] = ModelField(default={})
    model: str = ModelField()    
    
    class Config:
        database_type="postgres"
    
    async def evaluate(self, response: str):
        return await evaluate_prompt(task=self.task, response=response)
