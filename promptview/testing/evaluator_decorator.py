from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, List, Literal, Awaitable, Tuple, TypeVar

from promptview.block import Block
from promptview.testing.test_models import Evaluation, EvaluatorConfig, TurnEvaluator    

if TYPE_CHECKING:
    from promptview.model.version_control_models import Turn
    from promptview.testing.test_models import TestCase, TestRun



    
    





evaluator_store = {}



class EvalCtx:
    test_case: "TestCase"
    test_run: "TestRun"
    config: EvaluatorConfig
    
    
    def __init__(self, test_case: "TestCase", test_run: "TestRun", config: EvaluatorConfig):
        self.test_case = test_case
        self.test_run = test_run
        self.config = config


class EvaluatorCall:
    
    def __init__(self, config: EvaluatorConfig):
        self.func = ev
        
    async def __call__(self, config: EvaluatorConfig, ref_turn: "Turn", test_turn: "Turn", test_case: "TestCase"):
        return await self.func(config, ref_turn, test_turn, test_case)


TURN_MODEL = TypeVar("TURN_MODEL", bound="Turn", covariant=True)
    
# def evaluator(
#     func: Callable[["EvalCtx", TURN_MODEL, TURN_MODEL], Awaitable[Tuple[float, dict]]] | Callable[["EvalCtx", TURN_MODEL, TURN_MODEL], Awaitable[float]]
# ) -> Callable[["TestCase", "TestRun", EvaluatorConfig, TURN_MODEL, TURN_MODEL], Awaitable[Evaluation]]:
    
#     @wraps(func)
#     async def decorator(test_case: "TestCase", test_run: "TestRun", config: EvaluatorConfig, ref_turn: TURN_MODEL, test_turn: TURN_MODEL) -> Evaluation:        
#         ctx = EvalCtx(test_case, test_run, config)
#         res = await func(ctx, ref_turn, test_turn)
#         if isinstance(res, tuple):
#             score, metadata = res
#         else:
#             score = res
#             metadata = {}
#         return Evaluation(
#             evaluator=config.name,
#             score=score,
#             metadata=metadata,
#             turn_eval_id=test_turn.id,
#         )
#     evaluator_store[func.__name__] = decorator
#     return decorator


def evaluator(
    func: Callable[["EvalCtx", TURN_MODEL, TURN_MODEL], Awaitable[Tuple[float, dict]]] | Callable[["EvalCtx", TURN_MODEL, TURN_MODEL], Awaitable[float]]
) -> Callable[["TestCase", "TestRun", EvaluatorConfig], Callable[[TURN_MODEL, TURN_MODEL], Awaitable[Evaluation]]]:
    
    @wraps(func)
    def decorator(test_case: "TestCase", test_run: "TestRun", config: EvaluatorConfig) -> Callable[[TURN_MODEL, TURN_MODEL], Awaitable[Evaluation]]:        
        async def run_evaluator(ref_turn: TURN_MODEL, test_turn: TURN_MODEL) -> Evaluation:
            ctx = EvalCtx(test_case, test_run, config)
            res = await func(ctx, ref_turn, test_turn)
            if isinstance(res, tuple):
                score, metadata = res
            else:
                score = res
                metadata = {}
            return Evaluation(
                evaluator=config.name,
                score=score,
                metadata=metadata,
                turn_eval_id=test_turn.id,
            )
        return run_evaluator
    evaluator_store[func.__name__] = decorator
    return decorator
    
    
    
      








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