from functools import wraps
import inspect
from typing import (Any, AsyncGenerator, Callable, Dict, Generic, Type, TypeVar, ParamSpec)

from promptview.block.util import StreamEvent
from promptview.context import ExecutionContext

# from promptview.conversation.history import History


from promptview.block.block import Block
from .depends import  DependsContainer, resolve_dependency
from ..model.context import Context
from ..utils.function_utils import filter_args_by_exclude


P = ParamSpec('P')
R = TypeVar('R')


class StreamController2(Generic[P, R]):
    _name: str
    _complete: Callable[P, R]
    
    
    # def _set_history(self, history: History):
    #     history.init_last_session()
    #     return history
    
    
    def _filter_args_for_trace(self, *args: P.args, **kwargs: P.kwargs) -> dict[str, Any]:
        from promptview.llms import LLM
        _args, _kwargs = filter_args_by_exclude(args, kwargs, (LLM, Context))
        return {"args": _args, "kwargs": _kwargs}
    
    
    def _sanitize_output(self, output: Any) -> Any:
        if isinstance(output, Block):
            return output.content
        return output
    
    def build_execution_ctx(self) -> Context:
        curr_ctx: Context | None = Context.get_current(False)
        if curr_ctx is not None:
            ctx = curr_ctx.build_child(self._name)
        else:
            # raise ValueError("Context is not set")
            # ctx = Context().start()
            # ctx = Context()
            ctx = ExecutionContext(self._name)
        return ctx    
        

    async def _inject_dependencies(self, *args: P.args, **kwargs: P.kwargs) -> Dict[str, Any]:
        signature = inspect.signature(self._complete)
        injection_kwargs = {}
        for param_name, param in signature.parameters.items():
            default_val = param.default
            if isinstance(default_val, DependsContainer):
                dependency_func = default_val.dependency
                resolved_val = await resolve_dependency(dependency_func,  *args, **kwargs)
                # if isinstance(resolved_val, History):
                #     resolved_val = self._set_history(resolved_val)
                injection_kwargs[param_name] = resolved_val            
                
        return injection_kwargs
    
    
    
    # async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[StreamEvent, None]:
    #     execution_ctx = self.build_execution_ctx()
    #     async with execution_ctx.start_tracer(self._name, "prompt", inputs={}) as ctx:
    #         inspect.signature(self._complete).bind(*args, **kwargs)
    #         injection_kwargs = await self._inject_dependencies(*args, **kwargs)               
    #         kwargs.update(injection_kwargs)
    #         try:
    #             gen = self._complete(*args, **kwargs)
                    
    #             # yield chunk
    #             ctx.tracer.add_outputs({"response": self._sanitize_output(res)})
    #         except Exception as e:
    #             ctx.tracer.end(errors=str(e))
    #             raise e
            
            
            
            
import asyncio



    


STREAM_EVENT = TypeVar("STREAM_EVENT")
STREAM_RESPONSE = TypeVar("STREAM_RESPONSE")
P = ParamSpec("P")

class StreamController(Generic[STREAM_EVENT, STREAM_RESPONSE, P]):
    """
    Base class to control an async generator stream:
    - automatically exhausts it if desired
    - allows .send() and .throw() into it
    - override `run()` to implement your logic
    """
    
    _name: str
    _did_prime: bool = False
    _args: Any = ()
    _kwargs: Any = {}
    
    def __init__(
        self,                 
        # args: tuple,
        # kwargs: dict,
        response_type: Type[STREAM_RESPONSE] | None = None,
        *args: P.args,                 
        **kwargs: P.kwargs,        
    ):
        self._args = args
        self._kwargs = kwargs
        self._agen: AsyncGenerator[STREAM_EVENT, None] | None = None
        self._closed = False
        self.response_type = response_type
        
    @property
    def agen(self) -> AsyncGenerator[STREAM_EVENT, None]:
        if self._agen is None:
            raise ValueError("Generator not started")
        return self._agen

    async def start(self):
        """Starts the generator by calling the user-defined async generator."""
        self._agen = self.run(*self._args, **self._kwargs)
        await self.agen.asend(None)  # prime it

    async def next(self):
        """Get next value from generator."""
        return await self.agen.__anext__()

    async def send(self, value):
        """Send value into the generator."""
        return await self.agen.asend(value)

    async def throw(self, exc):
        """Throw exception into the generator."""
        return await self.agen.athrow(exc)

    async def close(self):
        """Close the generator."""
        if self.agen and not self._closed:
            await self.agen.aclose()
            self._closed = True

    async def exhaust(self):
        """Iterate over all values until exhausted."""
        results = []
        async for item in self.agen:
            results.append(item)
        return results

    async def __aenter__(self):
        await self.start()
        
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def run(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[STREAM_EVENT, None]:
        """
        Override this method in your subclass to implement your custom logic.
        This must be an async generator.
        """
        raise NotImplementedError("You must override the `run()` method.")
        yield
        
    # async def stream(self) -> AsyncGenerator[STREAM_EVENT, None]:
    #     await self.start()
    #     async for event in self.agen:
    #         if isinstance(event, StreamController):
    #             async for sub_event in event.stream():
    #                 yield sub_event
    #         else:
    #             yield event
    #     await self.close()
    
    def is_response_type_match(self, event: STREAM_EVENT) -> bool:
        if self.response_type is None:
            return False
        return isinstance(event, self.response_type)        
    
    
    async def stream(self) -> AsyncGenerator[STREAM_EVENT, None]:        
        self._agen = self.run(*self._args, **self._kwargs)        
        response = None
        try:
            while event:= await self.send(response):
                try:
                    response = None
                    if isinstance(event, StreamController):                    
                        sub_gen = event
                        async for sub_event in sub_gen.stream():
                            if sub_gen.is_response_type_match(sub_event):
                                # if response is not None:
                                    # raise ValueError("Multiple responses found.\n", "current response:\n", response, "new response:\n", sub_event)
                                response = sub_event
                            yield sub_event                    
                    
                    else:
                        yield event                              
                except Exception as e:
                    await self.throw(e)
        except StopAsyncIteration:
            print("STOPPED", self._name)
            return      
        finally:
            await self.close()

        
        
#     @classmethod
#     def build_decorator(cls):
#         def decorator() -> Callable[
#             [Callable[P, AsyncGenerator[STREAM_EVENT, None]]],
#             Callable[P, StreamController[STREAM_EVENT, P]]
#         ]:    
#             def decorator_inner(func: Callable[P, AsyncGenerator[STREAM_EVENT, None]]) -> Callable[P, StreamController[STREAM_EVENT, P]]:        
#                 @wraps(func)
#                 def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamController[STREAM_EVENT, P]:
#                     stream_controller = cls(*args, **kwargs)
#                     stream_controller._name = func.__name__
#                     stream_controller.run = func
#                     return stream_controller
#                 return wrapper    
#             return decorator_inner
#         return decorator
            
            
            
# stream = StreamController.build_decorator()           
            
            
def stream(
    response_type: Type[STREAM_RESPONSE] | None = None,
    ) -> Callable[
    [Callable[P, AsyncGenerator[STREAM_EVENT, None]]],
    Callable[P, StreamController[STREAM_EVENT, STREAM_RESPONSE, P]]
]:    
    def decorator(func: Callable[P, AsyncGenerator[STREAM_EVENT, None]]) -> Callable[P, StreamController[STREAM_EVENT, STREAM_RESPONSE, P]]:        
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamController[STREAM_EVENT, STREAM_RESPONSE, P]:
            stream_controller = StreamController(response_type, *args, **kwargs)
            stream_controller._name = func.__name__
            stream_controller.run = func
            return stream_controller
        return wrapper    
    return decorator