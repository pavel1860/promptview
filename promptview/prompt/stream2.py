from functools import wraps
import inspect
from typing import Any, AsyncGenerator, Callable, ParamSpec, Union, AsyncIterator, Optional, Generic
from typing_extensions import TypeVar

from promptview.prompt.events import Event



class StreamResponse:
    
    def __init__(self, value: Any):
        self.value = value
        
    def __str__(self):
        return str(self.value)
    
    def __repr__(self):
        return f"StreamResponse({self.value})"
    
    
CHUNK = TypeVar("CHUNK")
RESPONSE = TypeVar("RESPONSE")


class GeneratorFrame(Generic[CHUNK, RESPONSE]):
    def __init__(self, agen: AsyncGenerator[CHUNK, RESPONSE], accumulator: RESPONSE):
        self.agen = agen
        self.accumulator = self._init_accumulator(accumulator)
        self.started = False
        self.index = 0

    async def advance(self, value: CHUNK | None = None):
        self.index += 1
        if not self.started:
            self.started = True
            return await self.agen.__anext__()
        else:
            # return await self.agen.asend(self.accumulator)
            return await self.agen.asend(value or self.accumulator)
        
        
    def _init_accumulator(self, acc) -> Any:
        if acc is None:
            return ""
        elif callable(acc):
            return acc()
        else:
            return acc
        
    def try_append(self, value: Any):
        # Try using append or += for accumulation
        try:
            self.accumulator.append(value)
        except AttributeError:
            try:
                self.accumulator += value
            except Exception:
                pass  # Optionally: raise or log a warning

P = ParamSpec("P")



class StreamController(Generic[P, CHUNK, RESPONSE]):
    def __init__(
        self,
        name: str | None = None,
        agen: Union[AsyncGenerator[CHUNK | RESPONSE, RESPONSE], Callable[[], AsyncGenerator[CHUNK, RESPONSE]]] | None = None,
        accumulator: RESPONSE | Callable[[], RESPONSE] | None = None
    ):
        self._name = name
        self._stack = []
        self._initial_gen = agen or self.stream
        self._accumulator_factory = accumulator
        self._raise_on_next = False
        
        
    @property
    def response(self) -> RESPONSE:
        return self.current.accumulator
        
    async def stream(self, *args: P.args, **kwargs: P.kwargs) -> AsyncGenerator[Any, None]:
        """
        Override this method in your subclass to implement your custom logic.
        This must be an async generator.
        """
        pass
        yield
        
        
    @property
    def current(self) -> Any:
        if not self._stack:
            raise ValueError("No current generator")
        return self._stack[-1]

        
    def __await__(self):
        async def _consume():
            async for _ in self:
                pass
            return self.current.accumulator
        return _consume().__await__()


    def __aiter__(self) -> AsyncIterator[Any]:
        self._stack = [self.build_frame()]
        return self

    async def __anext__(self) -> Any:
        frame_response = None
        if self._raise_on_next:
            self._raise_on_next = False
            raise StopAsyncIteration(self.current.accumulator)
        while self._stack:
            try:
                value = await self.current.advance(frame_response)
                frame_response = None
                
                if isinstance(value, StreamController):
                    self._stack.append(value.build_frame())
                    continue

                # Attempt to append to the accumulator
                self.current.try_append(value)

                return value

            except StopAsyncIteration as e:
                if len(self._stack) == 1:
                    raise e
                    # self._raise_on_next = True                    
                    # return self.current.accumulator
                frame = self._stack.pop()
                frame_response = frame.accumulator
                
                if hasattr(e, "value") and e.value is not None:
                    self._accumulator = e.value

        raise StopAsyncIteration

    def _wrap(self, value: Any) -> GeneratorFrame:
        if inspect.isasyncgenfunction(value):
            value = value()
        if not inspect.isasyncgen(value):
            raise TypeError(f"{value} is not an async generator")
        return GeneratorFrame(value, self._accumulator_factory)
    
    def build_frame(self) -> GeneratorFrame:
        if inspect.ismethod(self._initial_gen):
            return GeneratorFrame(self._initial_gen(), self._accumulator_factory)
        else:
            return GeneratorFrame(self._initial_gen, self._accumulator_factory)


    async def stream_events(self):
        event = Event(type="stream_start", payload=None, index=0)
        yield event

        async for chunk in self:
            event = Event(type="message_delta", payload=chunk, index=self.current.index)
            yield event

        event = Event(type="stream_end", payload=self.current.accumulator, index=self.current.index)
        yield event



P = ParamSpec("P")
T = TypeVar("T")

def stream(
    accumulator: Optional[Union[Any, Callable[[], Any]]] = None
) -> Callable[[Callable[P, AsyncGenerator[Any, Any]]], Callable[P, StreamController]]:
    def decorator(
        func: Callable[P, AsyncGenerator[Any, Any]]
    ) -> Callable[P, StreamController]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> StreamController:
            agen = func(*args, **kwargs)
            return StreamController(name=func.__name__, agen=agen, accumulator=accumulator)
        return wrapper
    return decorator