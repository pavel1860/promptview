import inspect
from typing import (Any, Awaitable, Callable, Concatenate, Generator, Generic, List, Literal, Type,
                    TypedDict, TypeVar, ParamSpec, AsyncGenerator)
from promptview.llms.tracer import Tracer
from promptview.prompt.controller import Controller



P = ParamSpec('P')
R = TypeVar('R')
YieldType = TypeVar('YieldType')
# class Agent(Generic[P, YieldType]):   
class Agent(Controller[P, AsyncGenerator[YieldType, None]]):

    # _complete: Callable[P, AsyncGenerator[YieldType, None]]    
        
    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[YieldType, None]:
        injection_kwargs = await self._inject_dependencies(*args, **kwargs)
        with Tracer(
            name=self._name,
            inputs= {"args": args,"kwargs": kwargs},
            # session_id=context.session_id,
            # tracer_run=tracer_run
        ) as tracer_run:
            async for msg in self._complete(*args, **kwargs, **injection_kwargs):
                yield msg






def agent(
    **kwargs: Any
) -> Callable[[Callable[P, AsyncGenerator[YieldType, None]]], 'Agent[P, YieldType]']:
    """
    Decorator to create an Agent from a generator function.

    Args:
        **kwargs: Arbitrary keyword arguments to configure the Agent.

    Returns:
        A decorator that transforms a generator function into an Agent instance.
    """
    
    def decorator(func: Callable[P, AsyncGenerator[YieldType, None]]) -> 'Agent[P, YieldType]':
        # Initialize the Agent with provided keyword arguments
        agent = Agent(
            **kwargs
        )
        # Assign the generator function to the agent
        agent._name = func.__name__
        agent._complete = func
        return agent
        
    return decorator


# def agent(
#     **kwargs: Any
# )-> Callable[[Callable[P, R]], Agent[P, R]]:
    
#     def decorator(func: Callable[P, R]) -> Agent[P,R]:
#         agent = Agent(
#                 # model=model, #type: ignore                
#                 **kwargs
#             )
#         agent._name=func.__name__
#         agent._complete = func
#         return agent        
#     return decorator