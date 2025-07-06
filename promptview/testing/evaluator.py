from typing import TYPE_CHECKING, Any, List, Literal
from pydantic import BaseModel, Field
from promptview.llms.llm3 import OutputModel
from promptview.model.fields import KeyField
from promptview.prompt import prompt, Block, Depends
from promptview.llms import LLM
from promptview.testing.test_models import Evaluation, EvaluatorConfig    
if TYPE_CHECKING:
    from promptview.testing.test_models import TestCase


class EvalResult(OutputModel):
    reasoning: str = Field(..., description="step by step reasoning about the response, differences between expected and actual output and is it confirms with the requirements")
    score: int = Field(default=-1, description="score between 0 and 10")
    
    


@prompt()
async def prompt_score_evaluator(
    test_case: Any, 
    message: Block, 
    response: Block, 
    expected: Block,
    config: EvaluatorConfig,
    llm: LLM = Depends(LLM)
    ):
    
    if response is None:
        raise ValueError("Response is not set")
    if message is None:
        raise ValueError("Message is not set")
    if expected is None:
        raise ValueError("Expected is not set")
    
    with Block(role="system") as sys:
        sys([
            "You are an expert evaluator tasked with assessing the response of an AI assistant to a user's query.",
            "Your purpose is to evaluate responses and act as 'LLM as a judge'.",
        ])
        with sys("Task"):
            sys([
                "the user will send an output of for you to evaluate. you should evaluate it."
                "you should evaluate the response of an agent based on the expected output.",
                "you should return a score between 0 and 10."
            ])
        with sys("Rules", style=["list"]):
            sys([
                "remember that you are an evaluator, that is the only purpose of your output.",
            ])

    with Block(role="user") as usr:
        with usr("Test Case"):
            usr(test_case.description)
            with usr("Input"):
                usr /= message
            with usr("Response"):
                usr /= response
            with usr("Expected"):
                usr /= "can be one of the following:"
                with usr(style=["list"]):
                    for exp in expected:
                        usr /= exp
                
    res = await llm(sys, usr).complete(EvalResult)
    
    evaluation = Evaluation(
        evaluator=config.name,
        reasoning=res.reasoning,
        score=res.score,
        run_id=res.block().run_id,
    )
    return evaluation
    
    


evaluator_store = {
        "prompt_score": prompt_score_evaluator
    }




async def evaluate(        
        test_case: "TestCase", 
        message: Block, 
        response: Block, 
        expected: Block,
        config: EvaluatorConfig, 
    ) -> Evaluation:
    evaluator = evaluator_store[config.name]
    evaluation = await evaluator(
                    test_case=test_case,
                    message=message,
                    response=response,
                    expected=expected,
                    config=config
                )
    return evaluation