from functools import wraps
import inspect
from typing import Any, AsyncGenerator, Callable, ParamSpec, Union, AsyncIterator, Optional
from typing_extensions import TypeVar

class GeneratorFrame:
    def __init__(self, agen: AsyncGenerator):
        self.agen = agen
        self.started = False

    async def advance(self, value: Any):
        if not self.started:
            self.started = True
            return await self.agen.__anext__()
        else:
            return await self.agen.asend(value)

class AsyncStreamWrapper:
    def __init__(
        self,
        agen: Union[AsyncGenerator, Callable[[], AsyncGenerator]],
        accumulator: Optional[Union[Any, Callable[[], Any]]] = None
    ):
        self._stack = []
        self._initial_gen = agen
        self._accumulator = self._init_accumulator(accumulator)
        
        
    @property
    def current(self) -> Any:
        if not self._stack:
            raise ValueError("No current generator")
        return self._stack[-1]

    def _init_accumulator(self, acc) -> Any:
        if acc is None:
            return ""
        elif callable(acc):
            return acc()
        else:
            return acc
        
    def __await__(self):
        async def _consume():
            async for _ in self:
                pass
            return self._accumulator
        return _consume().__await__()


    def __aiter__(self) -> AsyncIterator[Any]:
        self._stack = [self._wrap(self._initial_gen)]
        return self

    async def __anext__(self) -> Any:
        while self._stack:
            try:
                value = await self.current.advance(self._accumulator)
                
                if isinstance(value, AsyncStreamWrapper):
                    self._stack.append(self._wrap(value._initial_gen))
                    continue

                # Attempt to append to the accumulator
                self._try_append(value)

                return value

            except StopAsyncIteration as e:
                self._stack.pop()
                if hasattr(e, "value") and e.value is not None:
                    self._accumulator = e.value

        raise StopAsyncIteration

    def _wrap(self, value: Any) -> GeneratorFrame:
        if inspect.isasyncgenfunction(value):
            value = value()
        if not inspect.isasyncgen(value):
            raise TypeError(f"{value} is not an async generator")
        return GeneratorFrame(value)

    def _try_append(self, value: Any):
        # Try using append or += for accumulation
        try:
            self._accumulator.append(value)
        except AttributeError:
            try:
                self._accumulator += value
            except Exception:
                pass  # Optionally: raise or log a warning

    async def stream_events(self):
        yield {"type": "stream_start"}

        async for chunk in self:
            yield {"type": "stream_delta", "value": chunk}

        yield {"type": "stream_end", "final_value": self._accumulator}



P = ParamSpec("P")
T = TypeVar("T")

def stream(
    accumulator: Optional[Union[Any, Callable[[], Any]]] = None
) -> Callable[[Callable[P, AsyncGenerator[Any, Any]]], Callable[P, AsyncStreamWrapper]]:
    def decorator(
        func: Callable[P, AsyncGenerator[Any, Any]]
    ) -> Callable[P, AsyncStreamWrapper]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> AsyncStreamWrapper:
            agen = func(*args, **kwargs)
            return AsyncStreamWrapper(agen, accumulator)
        return wrapper
    return decorator