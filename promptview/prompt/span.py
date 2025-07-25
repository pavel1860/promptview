from typing import Any, Callable, Optional, Union, AsyncGenerator
from functools import wraps
import time
import inspect
from pydantic import BaseModel

from promptview.prompt.depends import DependsContainer, resolve_dependency
from promptview.prompt.stream2 import AsyncStreamWrapper

# Assuming AsyncStreamWrapper, DependsContainer, and resolve_dependency are available

class SpanController:
    def __init__(
        self,
        span_func: Callable[..., AsyncGenerator],
        *args,
        accumulator: Optional[Union[Any, Callable[[], Any]]] = None,
        **kwargs,
    ):
        self.span_func = span_func
        self.span_args = args
        self.span_kwargs = kwargs
        self.accumulator_factory = accumulator
        self._start_time = None
        self._end_time = None
        self._trace_id = id(self)
        self._stream: Optional[AsyncStreamWrapper] = None

    async def _resolve_dependencies(self):
        signature = inspect.signature(self.span_func)
        bound = signature.bind_partial(*self.span_args, **self.span_kwargs)
        bound.apply_defaults()

        dep_kwargs = {}
        for name, param in signature.parameters.items():
            val = bound.arguments.get(name, param.default)
            if isinstance(val, DependsContainer):
                dep_kwargs[name] = await resolve_dependency(val.dependency)
            elif name not in bound.arguments:
                dep_kwargs[name] = val

        return inspect.BoundArguments(signature, bound.arguments | dep_kwargs)

    async def _init_stream(self):
        self._start_span()
        resolved_args = await self._resolve_dependencies()
        gen = self.span_func(*resolved_args.args, **resolved_args.kwargs)        
        self._stream = AsyncStreamWrapper(gen, self.accumulator_factory)

    def _start_span(self):
        self._start_time = time.time()
        print(f"[Span Start] {self.span_func.__name__} (trace_id={self._trace_id})")

    def _end_span(self, error: Optional[Exception] = None):
        if self._end_time is None:
            self._end_time = time.time()
            duration = self._end_time - self._start_time
            if error:
                print(f"[Span Error] {self.span_func.__name__}: {error}")
            print(f"[Span End] {self.span_func.__name__} (duration={duration:.2f}s)")

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._stream:
            await self._init_stream()
        try:
            return await self._stream.__anext__()
        except StopAsyncIteration:
            self._end_span()
            raise
        except Exception as e:
            self._end_span(error=e)
            raise


    def stream_events(self):
        async def event_stream():
            if not self._stream:
                await self._init_stream()
            async for event in self._stream.stream_events():
                yield event
            self._end_span()
        return event_stream()

    def __await__(self):
        async def await_result():
            if not self._stream:
                await self._init_stream()
            try:
                result = await self._stream
                self._end_span()
                return result
            except Exception as e:
                self._end_span(error=e)
                raise
        return await_result().__await__()


# Decorator for span-enabled async generators using composition
def span(
    accumulator: Optional[Union[Any, Callable[[], Any]]] = None
) -> Callable[[Callable[..., AsyncGenerator]], Callable[..., SpanController]]:
    def decorator(func: Callable[..., AsyncGenerator]) -> Callable[..., SpanController]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> SpanController:
            return SpanController(func, *args, accumulator=accumulator, **kwargs)
        return wrapper
    return decorator

