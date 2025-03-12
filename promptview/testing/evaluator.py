from pydantic import BaseModel, Field
from promptview.prompt import prompt, Depends, Block, LLMBlock, OutputModel
# from promptview.prompt import Block as blk
from promptview.prompt import LLMBlock as blk
from promptview.llms import OpenAiLLM
from promptview.model.model import Model
from promptview.model.fields import ModelField



class EvalResponse(OutputModel):
    reasoning: str = Field(..., description="step by step reasoning about the evaluation of the response")
    score: int = Field(..., description="the score of the response. should be an integer number between 1 and 10")

    @classmethod
    def render(cls) -> Block | None:
        with blk("Rules", style=["list"]) as b:
            b += "you have to use the output format and the reasoning to evaluate the response"
            b += "you have to give a true score for the response."
            return b



@prompt()
async def evaluate_prompt(task: str, response: str, llm: OpenAiLLM = Depends(OpenAiLLM)):

    with blk("""
        you are a helpful assistant that evaluates the response.
        You need to evaluate the response based on the given task and rules.
    """, role="system") as sm:
        with sm("Task"):
            sm += task
        EvalResponse.to_block(sm)
    
    with blk("Response to evaluate", role="user") as target:
        target += response
    
    res = await llm(sm + target).output_format(EvalResponse)
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
